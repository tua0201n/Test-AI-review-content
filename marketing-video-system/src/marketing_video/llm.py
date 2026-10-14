"""LLM adapters for discovery; Gemini is the default provider."""
import asyncio
from importlib.resources import files
from .models import ExplorationPlan, ProductBrief
from .settings import Settings

SYSTEM = files("marketing_video").joinpath("prompts/discovery.txt").read_text(encoding="utf-8")


class Planner:
    def __init__(self, settings=None):
        from browser_use import ChatBrowserUse, ChatOpenAI, ChatGoogle
        self.settings = settings or Settings.from_env()
        self.provider = self.settings.provider
        name = self.settings.model
        if not name:
            raise ValueError("Set MODEL_NAME in .env")
        if self.provider in {"google", "gemini"}:
            key = self.settings.google_api_key.get_secret_value()
            if not key:
                raise ValueError("Missing GOOGLE_API_KEY. Fill it in marketing-video-system/.env")
            self.llm = ChatGoogle(model=name, api_key=key, temperature=0.2, max_output_tokens=4096, max_retries=2,
                http_options={"timeout": self.settings.llm_timeout * 1000})
        elif self.provider == "browser-use":
            key = self.settings.browser_use_api_key.get_secret_value()
            if not key:
                raise ValueError("Missing BROWSER_USE_API_KEY")
            self.llm = ChatBrowserUse(model=name, api_key=key, timeout=self.settings.llm_timeout, max_retries=2)
        else:
            key = self.settings.openai_api_key.get_secret_value()
            if not key:
                raise ValueError("Missing OPENAI_API_KEY")
            self.llm = ChatOpenAI(model=name, api_key=key, base_url=self.settings.openai_base_url or None,
                                 timeout=self.settings.llm_timeout)
        self.model = name

    async def invoke(self, instruction, data, output_schema, system_prompt=None):
        import json
        from browser_use.llm.messages import SystemMessage, UserMessage
        print("LLM:", output_schema.__name__, "model=" + self.model, flush=True)
        messages = [
            SystemMessage(content=system_prompt or SYSTEM),
            UserMessage(content=instruction + "\nDATA:\n" + json.dumps(data, ensure_ascii=False)),
        ]
        for attempt in range(3):
            try:
                result = await asyncio.wait_for(self.llm.ainvoke(messages, output_format=output_schema),
                                                timeout=self.settings.llm_timeout)
                return result.completion
            except Exception as exc:
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                transient = isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or code in {429, 500, 502, 503, 504}
                if not transient or attempt == 2:
                    raise
                print(f"LLM: transient {type(exc).__name__}; retry {attempt + 1}/2", flush=True)
                await asyncio.sleep(2 ** (attempt + 1))

    async def plan(self, page):
        from .discovery import SEARCH, PASSIVE, RISK, same_site, detail_navigation, permitted
        from urllib.parse import urlparse
        candidates = []
        for c in page.controls:
            if c.tag == "input" and SEARCH.search(c.label + " " + c.type):
                score = 0
            elif c.role == "tab" or c.tag == "summary" or c.expanded is not None:
                score = 1
            elif c.tag == "select" or (c.tag in {"button", "div"} and (PASSIVE.search(c.label) or c.interaction_hint in {"tab", "filter", "disclosure", "media"})):
                score = 2
            elif c.tag == "a" and detail_navigation(c,page.url) and not urlparse(c.href).fragment:
                score = 3
            else:
                continue
            candidates.append((score,c))
        candidates.sort(key=lambda x:x[0])
        candidates = [(score,c) for score,c in candidates if (not RISK.search(c.label+" "+c.href) or detail_navigation(c,page.url)) and not c.form_submit]
        controls = [{"id":c.id,"tag":c.tag,"label":c.label,"type":c.type,"href":c.href,
                     "role":c.role,"interaction_hint":c.interaction_hint,"options":c.options[:8]} for _,c in candidates[:12]]
        links = list(dict.fromkeys(c.href for c in page.controls if c.tag=="a" and same_site(c.href,page.url) and not urlparse(c.href).fragment))[:12]
        data = {"id":page.id,"url":page.url,"title":page.title,"text":page.text[:1600],
                "requires_auth":page.requires_auth,"controls":controls,"known_urls":links}
        return await self.invoke("Select up to 2 safe functionality probes from the listed control IDs. Infer the product type and useful user tasks from this page. Prioritize result-producing controls relevant to this product over language/notifications/sidebar navigation. Do not assume the website is an education platform. Prioritize functional pages in known_urls before upgrade/login/signup/policy pages. Do not choose homepage anchor-only navigation. For search, choose a distinctive word from one listed result title rather than generic terms that match every result. Keep explanations concise.", data, ExplorationPlan)

    async def brief(self, report):
        data = {"input_url": report.input_url,
            "pages": [{"id": p.id, "url": p.url, "title": p.title, "text": p.text[:1800], "requires_auth": p.requires_auth} for p in report.pages],
            "probes": [{"id": p.id, "feature": p.request.feature, "status": p.status, "reason": p.reason, "changes": p.observed_changes} for p in report.probes]}
        return await self.invoke("Write a product research brief grounded in the evidence. All source_page_ids must exist. Only demonstrated probe IDs may be recommended. Explicitly state functionality blocked by login and cases with no observable result.", data, ProductBrief)
