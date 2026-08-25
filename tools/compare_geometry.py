from straddle_replica.cli import main


raise SystemExit(main(["compare-geometry", *__import__("sys").argv[1:]]))
