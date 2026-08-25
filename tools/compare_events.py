from straddle_replica.cli import main


raise SystemExit(main(["compare-events", *__import__("sys").argv[1:]]))
