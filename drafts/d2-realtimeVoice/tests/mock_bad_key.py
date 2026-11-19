"""A rejected API key (HTTP 401) produces a readable error message."""
import asyncio, http, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # folder containing realtime_voice.py
from websockets.asyncio.server import serve
WRAP = r'''
import asyncio, sys, types
sys.path.insert(0, sys.argv[2])
import realtime_voice as rv
rv.api_key = lambda: "sk-wrong"; rv.LIVE["url"] = sys.argv[1]
src = open(rv.__file__).read().split('if __name__ == "__main__":')[1]
sys.argv = ["realtime_voice.py", "--headphones"]
exec("import textwrap\n" + "exec(textwrap.dedent(" + repr(src) + "), vars(rv))")
'''
def reject(conn, req):
    return conn.respond(http.HTTPStatus.UNAUTHORIZED, '{"error": {"message": "Incorrect API key provided: sk-wrong."}}\n')
async def main():
    async with serve(lambda ws: None, "127.0.0.1", 0, process_request=reject) as srv:
        port = srv.sockets[0].getsockname()[1]
        p = await asyncio.create_subprocess_exec(sys.executable, "-c", WRAP, f"ws://127.0.0.1:{port}/v1/live/sessions", str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = await p.communicate(); print(out.decode()[-400:]); print("exit", p.returncode)
asyncio.run(main())
