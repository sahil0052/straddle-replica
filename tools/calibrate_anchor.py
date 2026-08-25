from straddle_replica.cli import main


raise SystemExit(main(["calibrate-anchor", *__import__("sys").argv[1:]]))
