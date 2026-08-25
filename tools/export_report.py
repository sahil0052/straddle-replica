from straddle_replica.cli import main


raise SystemExit(main(["export-report", *__import__("sys").argv[1:]]))
