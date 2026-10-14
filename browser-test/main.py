from auto_review import main, parse_args
import asyncio

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
