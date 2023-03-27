FROM python:3.10.10-slim

WORKDIR /usr/spp/src

COPY extract_load.py ./

CMD ["python3", "./extract_load.py", "--configfile", "psql.config", "--action backup"]
CMD ["python3", "./extract_load.py", "--configfile", "psql.config", "--action restore"]