# Easterobot

Discord bot for Easter.

## Download source

```bash
git clone https://github.com/Dashstrom/easterobot
cd easterobot
```

## Edit configuration

```bash
cp easterobot/data/config.yml.exemple easterobot/data/config.yml
nano easterobot/data/config.yml
```

## How to install docker

On rasbian run these command before install docker :

```bash
sudo apt install --reinstall raspberrypi-bootloader raspberrypi-kernel
sudo reboot
```

Install docker from script

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker "${USER}"
sudo apt remove docker-ce
pip3 install docker-compose
```

## Some usefull commands

```bash
docker compose up -d --build
docker compose logs -f
docker compose exec bot bash
docker compose stop
docker compose down --volumes --rmi 'all'
```

## Generate images

```bash
pip3 install requirements-tools.txt
python3 tools/cropping.py images/eggs.png images/eggs -s 13
```

## Run test

```bash
pip3 install requirements-dev.txt
isort .
black .
tox .
```

## Unintsall

```bash
sudo apt-get purge docker-ce
sudo rm -rf /var/lib/docker
```

## Update

```bash
docker compose stop
git pull
nano easterobot/data/config.yml
docker compose up -d --build
```

## Backups

Export backups

```bash
docker compose stop
docker run --rm -v "easterobot_database:/database" -v "easterobot_logs:/logs" -v "$(PWD):/backup" ubuntu tar czvf /backup/backup.tar.gz -C / database logs 
docker compose up -d
```

Import backups

```bash
docker compose stop
docker run --rm -v "easterobot_database:/database" -v "easterobot_logs:/logs" -v "$(PWD):/backup" ubuntu bash -c "cd / && rm -rf /{database,logs}/* && tar xvfP /backup/backup.tar.gz"
docker compose up -d
```
