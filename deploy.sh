#!/bin/bash

cp volume-rotary-encoder /usr/local/bin/volume-rotary-encoder
chmod +x /usr/local/bin/volume-rotary-encoder

if [[ :$PATH: != *:"/usr/local/bin":* ]] ; then
    PATH=$PATH:/usr/local/bin
fi

cp volume-rotary-encoder.service /etc/systemd/system/volume-rotary-encoder.service
chmod +x /etc/systemd/system/volume-rotary-encoder.service

systemctl enable volume-rotary-encoder
systemctl start volume-rotary-encoder
