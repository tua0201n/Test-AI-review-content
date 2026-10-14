# Kiến trúc hiện tại

## Luồng Task 1

~~~text
URL + .env
    ↓
Playwright: mở trang, thu thập nội dung và controls
    ↓
Gemini: chọn tối đa 2 probe/trang và URL nên khảo sát tiếp
    ↓
Bộ thực thi: kiểm tra target + click/type/select
    ↓
Bằng chứng: ảnh trước/sau, thay đổi URL/nội dung/trạng thái
    ↓
Gemini: tổng hợp product brief từ bằng chứng đã thu thập
    ↓
artifacts/runs/<run-id>/discovery.json + discovery.md
~~~

Gemini dùng ChatGoogle từ browser-use với GOOGLE_API_KEY, gọi trực tiếp Gemini API. Browser Use Agent chưa điều khiển khảo sát ở task này; Playwright thực thi probe được chọn. Việc ghi hình và dựng video theo cảnh thuộc các task tiếp theo.

## Module

| Module | Vai trò |
|---|---|
| settings.py | Nạp .env, kiểm tra giới hạn, xác định root/runtime/artifacts |
| models.py | Schema Pydantic cho controls, probe, bằng chứng và product brief |
| llm.py | Chọn adapter từ MODEL_PROVIDER, gọi structured output |
| prompts/discovery.txt | Chỉ dẫn khảo sát và quy tắc grounding cho LLM |
| discovery.py | Crawl có giới hạn, thử thao tác, lưu và kiểm tra bằng chứng |
| __main__.py | CLI check, test-llm, discover |

## Dữ liệu mỗi run

- page-*-plan.json: kế hoạch probe, nguồn LLM hoặc heuristic theo analysis_status.
- screenshots/page-*.png: trang đã khảo sát.
- screenshots/probe-*-before.png, probe-*-after.png: kết quả trước/sau.
- discovery.json: hồ sơ có schema_version, status và analysis_status.
- discovery.md: báo cáo để người phát triển đọc và kiểm tra.
- llm-test-*/result.json: kết quả kiểm tra structured response từ model.

## Quyết định marketing ở bước kế tiếp

Chỉ chọn probe có bằng chứng demonstrated làm ứng viên demo. Trạng thái này chỉ chứng minh thay đổi giao diện; Task 2 phải bổ sung checkpoint cụ thể theo nghiệp vụ để tránh nhầm một menu mở được với toàn bộ chức năng đã hoạt động.

Khi API lỗi, ngừng gọi lỗi lặp lại, tiếp tục thu thập browser evidence và ghi partial / unavailable. Heuristic không tạo product brief AI.

## Cấu hình và model

Model cấu hình mặc định của dự án là gemini-3.5-flash-lite. Có thể đổi MODEL_NAME theo quyền truy cập của API key. Hệ thống không tự đổi model hoặc provider khi lỗi.

Tài liệu đối chiếu: https://ai.google.dev/gemini-api/docs/models và https://docs.browser-use.com/open-source/supported-models.


## Task 2: workflow thích ứng theo URL

~~~text
URL bất kỳ
  → discovery: trang/control/bằng chứng riêng của URL đó
  → đồ thị liên tục: bước B chỉ theo A nếu target B có trong kết quả A, trên cùng URL
  → Gemini suy luận loại sản phẩm, đối tượng và chọn 1–3 luồng có giá trị
  → compiler: không cho thêm ID lạ, nối trang không liên tục hoặc hành động chưa chứng minh
  → replay: một lần điều hướng ban đầu, thực hiện liên tục, kiểm tra từng bước
  → manifest ready_for_recording chỉ khi toàn bộ luồng đạt kiểm tra
~~~

Không có template Learn/Quest/Ranking hoặc URL mặc định trong engine. Product type là chuỗi do Gemini suy luận, không phải danh sách loại website cố định. Quy tắc thao tác sử dụng cấu trúc DOM, ARIA, trường search/filter và mục đích điều hướng. Chính sách tránh submit/write là chung cho mọi website. Session chỉ được nạp cho host được cấp.

Một liên kết mở chi tiết sản phẩm có thể là bước nghiệp vụ; không tự gán mọi liên kết thành "navigation". Filter loại kết quả có thể chỉ xóa dòng nên checkpoint hỗ trợ text_absent. Empty state không được chọn làm demo chính. Mỗi bước lưu source_probe_id, checkpoint và screenshot. Nếu một bước sai, dừng luồng ngay; không tiếp tục rồi báo đạt ở cuối.

prepare-demo URL điều phối discovery/plan/validation trong một run, ghi manifest ngay cả khi không đủ bằng chứng hoặc lỗi. plan-demo vẫn hỗ trợ tái sử dụng discovery.json đã hoàn tất. Schema demo-plan 2.0 hỗ trợ nhiều bước; validator đọc được plan 1.0 cũ.

Khả năng hiện tại: read-only click, nhập search và chọn filter. Website có control không có semantic rõ ràng, đăng nhập riêng hoặc tác vụ ghi dữ liệu có thể cần thêm bằng chứng/quyền truy cập. Engine ghi thiếu bằng chứng thay vì áp luồng cố định hoặc bịa thao tác. API và thời gian khám phá được giới hạn theo cấu hình.

URL đầu vào được giữ để truy xuất nguồn; resolved_url/site_url lưu đích chuẩn sau redirect. Điều này hỗ trợ URL đổi hostname (ví dụ sang www) mà vẫn giới hạn thao tác ở website đã quan sát.

## Task 3: storyboard bám bằng chứng

~~~text
manifest Task 2 ready_for_recording
  → khóa plan/validation/discovery trong cùng thư mục run
  → tạo evidence catalog cho danh tính, advertised claim và từng bước đã replay
  → Gemini viết storyboard theo ngôn ngữ, tỷ lệ và thời lượng yêu cầu
  → compiler kiểm tra ID, thời lượng, lợi ích và thứ tự đầy đủ của workflow
  → Gemini biên tập độc lập từng claim
  → storyboard ready hoặc needs_revision
~~~

`storyboard.py` không biết trước loại website. Cảnh demo nối với `flow_id` và `step_index` của Task 2; cảnh lợi ích nối với advertised claim của Task 1. `product_identity` chỉ hỗ trợ tên, loại sản phẩm và đối tượng, không hỗ trợ lời hứa về tốc độ, hiệu quả hay kết quả. Đầu ra này là hợp đồng đầu vào cho trình quay ở Task 4.

## Task 4: recorder theo workflow

~~~text
storyboard ready + plan/validation passed + session theo host
  → mở flow trong Chromium 1280×720
  → tìm lại target bằng fingerprint đã xác minh
  → animate con trỏ tới target và phát click pulse
  → thực hiện click/type/select read-only
  → kiểm tra lại checkpoint và lưu poster/trace
  → ghi raw flow WebM
  → FFmpeg tách clip theo mốc từng scene
  → recording-manifest ready hoặc failed
~~~

Recorder quay mỗi flow một lần để giữ trạng thái giữa các bước. Nó không yêu cầu biết website là khóa học, cửa hàng hay dashboard. Liên kết từ storyboard tới `flow_id` và `step_index` quyết định thao tác cần quay. Trace lưu tọa độ con trỏ, mốc bắt đầu/kết thúc và kết quả checkpoint để Task 5 có thể dựng lại một cách xác định.

## Task 5: composer media

~~~text
storyboard ready + recording manifest ready
  → TTS riêng cho từng scene và chuẩn hóa duration
  → render card cho hook/benefit/CTA
  → thêm lower-third vào clip demo
  → chuẩn hóa H.264 1280×720 30 fps
  → nối narration, tạo music bed và SRT
  → mux H.264 + AAC thành marketing-video.mp4
  → video-manifest ready hoặc failed
~~~

Composer kiểm tra recording thuộc đúng storyboard và chỉ đọc clip/poster nằm trong thư mục run. Timeline lấy trực tiếp từ duration từng scene. Cảnh narrative dùng poster sản phẩm làm nền mờ; cảnh demo giữ nguyên footage đã kiểm chứng. TTS quá dài, asset thiếu hoặc duration cuối sai đều làm run thất bại.

## Task 6: quality gate và delivery

~~~text
video-manifest ready
  → kiểm tra quan hệ storyboard/recording/video
  → kiểm tra scene, checkpoint, duration và stream media
  → đối chiếu SRT với toàn bộ voiceover
  → lấy khung giữa từng scene và đo brightness/contrast
  → tạo QA report và contact sheet
  → copy whitelist file, tạo provenance sạch và SHA-256
  → xuất thư mục deliverable + ZIP
~~~

Packaging dùng whitelist thay vì sao chép toàn bộ run. Vì vậy session, biến môi trường, raw browser state và đường dẫn nội bộ không đi vào deliverable. ZIP chỉ được tạo khi mọi quality gate đạt; checksum cho phép kiểm tra file không bị thay đổi sau khi bàn giao.
