"""Single source/frozen entry point; worker subprocesses never create a GUI."""
import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--worker-script':
        import runpy
        script = sys.argv[2]
        sys.argv = sys.argv[2:]
        runpy.run_path(script, run_name='__main__')
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        del sys.argv[1]
        from multigame import main as cli
        return cli()
    from multigame_gui import App
    App().mainloop()
    return 0

if __name__ == '__main__':
    sys.exit(main())
