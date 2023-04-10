# Easterobot

Discord bot for Easter.

## Download source

```bash
git clone https://github.com/Dashstrom/easterobot
cd easterobot
```

## Edit configuration

```bash
cp easterobot.yml.exemple easterobot.yml
vim easterobot.yml
```

## How to install docker

```bash
sudo apt-get update && sudo apt-get upgrade
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
pip install docker-compose
```

## Some usefull commands

```bash
docker compose up -d
docker compose ls
docker compose stop
docker compose down --volumes --rmi 'all'
```

## Generate images

```bash
pip install requirements-tools.txt
python3 tools/cropping.py images/eggs.png images/eggs -s 13
```
