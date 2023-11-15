FROM debian:bullseye-backports

RUN apt-get update && \
    apt-get install -y \
    bash \
    git \
    less \
    nano \
    python3 \
    python3-pip \
    time \
    verilator \
    vim \
    yosys

# RUN apt-get install -t bullseye-backports -y racket

# Install Rosette
# RUN raco pkg install --auto rosette

# Install PyRTL
RUN pip3 install pyparsing
RUN git clone https://github.com/pllab/PyRTL.git && cd PyRTL && git checkout blif-cells && pip3 install .

WORKDIR /mnt
