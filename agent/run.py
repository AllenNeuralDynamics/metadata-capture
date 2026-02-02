"""Entry point to run the metadata capture agent server."""

import uvicorn


def main():
    uvicorn.run(
        "agent.server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )


if __name__ == "__main__":
    main()
