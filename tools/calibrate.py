from straddle_replica.cli import main


raise SystemExit(main(["calibrate", *__import__("sys").argv[1:]]))
