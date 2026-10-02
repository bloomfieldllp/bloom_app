
ipconfig getifaddr en0
10.236.241.89
python -m pyftpdlib \
  --interface 0.0.0.0 \
  --port 2121 \
  --username dkp \
  --password 123456789 \
  --write \
  --directory "$HOME/A7III_FTP/incoming" \
  --range 50000-50010