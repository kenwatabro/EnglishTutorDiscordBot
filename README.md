## reload systemd
sudo systemctl daemon-reload

## start service
sudo systemctl start discordbot.service

## enable service
sudo systemctl enable discordbot.service

## check service status
sudo systemctl status discordbot.service

## check log
journalctl -u discordbot.service -f

## disable service
sudo systemctl disable discordbot.service

## stop bot
sudo systemctl stop discordbot.service


## restart bot
sudo systemctl restart discordbot.service

