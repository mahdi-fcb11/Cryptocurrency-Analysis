FROM python:3.8-slim
WORKDIR cryptocurrency_analysis/
RUN apt update
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt update
RUN apt install -y default-jre
RUN apt-get install -y openjdk-17-jdk
RUN export JAVA_HOME=$(readlink -f $(which java))

COPY . /cryptocurrency_analysis/

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
