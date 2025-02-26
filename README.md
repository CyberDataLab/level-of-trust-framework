<h1 align="center">LoTAF (Level of Trust Assessment Function)</h1>

LoTAF is an **open-source** trustworthy function for designing, deploying and ensuring that end-users' **trust requirements** are fulfilling during an **end-to-end** business relationship. By using LoTAF, you may declare trust as an **intent** to orchestrate **6G network services** and guarantee a Trust Level Agreement in a **multi-domain** and **multi-stakeholder** scenario. 

![Framework](https://github.com/CyberDataLab/level-of-trust-framework/blob/main/LoT_architecture.png)

## 🔧 Features

- 📡 **Real-time trust assurance reports**  
- 🔍 **Structured data representation using JSON and YANG data models**  
- 🧠 **Customized ontology for trust management and Computing Continuum**  
- 🔗 **Interoperability with Service Assurance IBN RFC 9417**  
- 🚀 **RESTful Public API for programmatic access**  
- 🐳 **Dockerized deployment for easy setup**  

## ⚙️ Installation

1. **Clone** the repository:
   ```bash
   git clone https://github.com/CyberDataLab/level-of-trust-framework.git

2. **Navigate** to the project directory:
    ```bash
    cd intent-assurance/dxagent-master/

3. **Determine** your installation approach:

**Option 1 (Recommended)**: Run our ad-hoc shell which contemplates your central processing unit, your deployment preferences, and create a virtual environment, and set required certificates for gNMI exporter and Kafka Bus. The installation and deploy is as follows:

#### 📊 DxAgent setup

This is the enhanced monitoring agent contemplated in LoTAF to continuously get real-time data. It is highly recommended to run `sudo ./setup.sh` to install every necessary dependency.

In order to uninstall everything installed in `setup.sh` except python3, run `sudo ./uninstall.sh`.

**Option 2**: Use the installation and deployment configuration from the baseline DxAgent. Follow the README.md file inside `cd intent-assurance/dxagent-master/`.

## 🕹️ Usage

1. **Start** the DxCollector service:

After running the DxAgent, it is required to launch DxCollector to observe health scores. DxCollector is an interface that collects the DxAgent data and stores it in json/yaml files while sending it to Kafka to process the information. The DxCollector must be launched in another terminal.

#### 🔍 DxCollector -- Commands

Note that both Kafka and JSON options can be activated at the same time.

* `dxcollector [-h] [-f <json|yaml>] [-o <filename>] [--kafka]`
   * `filename` defaults to `datos_exporter.{json/yaml}` 
   * `--kafka` enables kafka export.

#### 💻 DxCollector -- Important code

The following parameters should be configured on `intent-assurance/dxagent-master/agent/dxcollector.py`. This version deploys Kafka and GNMI server in local mode, but if you want to use an external Kafka Cluster, you will need to update the `KAFKA_BROKER` and `KAFKA_TOPIC` options.

* `GNMI_SERVER:` gNMI address.
* `GNMI_MODE:` Subscription mode:
   * `SAMPLE:` Receive data in time intervals.
   * `ON_CHANGE:` Receive data when data is different.
* `KAFKA_BROKER:` Address of the Kafka Broker.
* `KAFKA_TOPIC:` Topic to send the DxAgent data. 
* `XPATHS:` See [agent/gnmi/README.md](https://github.com/ekorian/dxagent/tree/master/agent/gnmi).

#### 📋 Requirements
The list of requirements are automatically installed during the `sudo ./setup.sh` script.

* `Protobuf 3.20.0`
   * pip install protobuf == 3.20.0
* `Pyyaml`  
   * pip install pyyaml
* `Cisco-gnmi`
   * pip install cisco-gnmi
* `Confluent_kafka`
   * pip install confluent_kafka

## 📜 License

LoTAF is **open-source** under the **GPL-3.0 license**. See the `LICENSE` file for details.


