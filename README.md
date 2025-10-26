Game Demo

This is a small pygame demo. A virtual environment is provided for convenience.

Quick start

1) Create and activate the virtual environment (recommended):

```bash
cd /Users/liyuwen/game_demo
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies and run the demo:

```bash
pip install -r requirements.txt
python3 main.py
```

Or simply run the included helper script (it will create/activate the venv, install deps and run):

```bash
./run.sh
```

Troubleshooting

- If you see "ModuleNotFoundError: No module named 'pygame'", make sure you are using the virtual environment created above (activate it with `source .venv/bin/activate`) or run `./run.sh` which handles activation and install.
