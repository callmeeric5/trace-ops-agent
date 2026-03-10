"""Export the compiled agent graph as Mermaid or PNG."""

import argparse

from backend.agent.graph import (
    export_compiled_graph_mermaid,
    export_compiled_graph_png,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export agent graph to Mermaid.")
    parser.add_argument(
        "--output",
        default="doc/agent_graph.mmd",
        help="Output .mmd path (default: doc/agent_graph.mmd)",
    )
    parser.add_argument(
        "--format",
        choices=["mmd", "png"],
        default=None,
        help="Export format. Defaults to output extension.",
    )
    args = parser.parse_args()

    fmt = args.format
    if fmt is None:
        if args.output.lower().endswith(".png"):
            fmt = "png"
        else:
            fmt = "mmd"

    if fmt == "png":
        export_compiled_graph_png(args.output)
        print(f"Exported PNG graph to {args.output}")
    else:
        export_compiled_graph_mermaid(args.output)
        print(f"Exported Mermaid graph to {args.output}")


if __name__ == "__main__":
    main()
