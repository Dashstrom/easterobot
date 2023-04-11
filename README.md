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

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker "${USER}"
sudo apt remove docker-ce
pip3 install docker-compose
```

## Some usefull commands

```bash
docker compose up -d
docker compose ls
docker compose stop
docker compose logs -f --tail 80
docker compose restart
docker compose down --volumes --rmi 'all'
```

## Generate images

```bash
pip install requirements-tools.txt
python3 tools/cropping.py images/eggs.png images/eggs -s 13
```

## Unintsall

```bash
sudo apt-get purge docker-ce
sudo rm -rf /var/lib/docker
```

## Update

```bash
docker compose down --volumes --rmi 'all'
git pull
docker compose up -d
```
