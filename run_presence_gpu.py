"""Optional, separate GPU prototype. No microphone, model or database is opened."""
import sys

if __name__ == "__main__":
    from jarvis.presence_gpu import main
    sys.exit(main())
