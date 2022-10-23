#!/bin/bash

ln -snf /usr/share/zoneinfo/UTC /etc/localtime && echo UTC > /etc/timezone

apt-get update
apt-get install -y ffmpeg imagemagick software-properties-common python3.8 python3-pip mysql-client libmysqlclient-dev

pip install -r requirements.txt


pip install python-dotenv ffmpeg-python mysqlclient