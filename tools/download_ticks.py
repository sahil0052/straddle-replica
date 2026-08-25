from straddle_replica.cli import main


raise SystemExit(main(["download-ticks", *__import__("sys").argv[1:]]))
