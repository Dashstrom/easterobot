# Easterobot

Discord bot for Easter.

```bash
git clone https://github.com/Dashstrom/easterobot
cd easterobot
pip install -r requirements.txt
# Edit the configuration file at easterobot/data/config.yml
export TOKEN="..."
python3 -m easterobot
```

Générer les images d'œufs :

```bash
python3 tools/cropping.py images/eggs.png images/eggs -s 13
```
