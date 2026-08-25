from straddle_replica.cli import main


raise SystemExit(main(["audit-ticks", *__import__("sys").argv[1:]]))
