# Virtual IoT Device (TATU / MQTT)

Dispositivo IoT virtual escrito em Python que simula um dispositivo real conversando com um gateway através de um broker MQTT, usando o protocolo **TATU**. O dispositivo se registra, responde a requisições `GET` e envia fluxos periódicos de dados (`FLOW`) com valores aleatórios.

---

## Visão geral


Ciclo de vida:

1. O dispositivo conecta ao broker e assina o tópico de comandos `dev/{device_id}`.
2. Publica o **handshake** (`CONNECT VALUE BROKER {json}`) em `dev/CONNECTIONS`, informando sua estrutura (id, localização e sensores).
3. Fica aguardando comandos:
   - `GET VALUE {sensor_id}` → responde uma única leitura.
   - `FLOW VALUE {sensor_id} {json}` → inicia (ou atualiza) um fluxo contínuo de coleta/publicação para aquele sensor.
4. As respostas são publicadas em `dev/{device_id}/RES`.

---

## Estrutura do projeto

```
.
├── Dockerfile
├── requirements.txt
└── app/
    ├── main.py           # Ponto de entrada: lê variáveis de ambiente e monta o dispositivo
    ├── device.py         # VirtualIoTDevice: cliente MQTT, handshake e tratamento de comandos
    ├── protocol.py       # Construção/parse das mensagens TATU
    └── sensor_worker.py  # SensorFlowWorker: thread de coleta/publicação por sensor
```

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Lê `BROKER_IP`, `BROKER_PORT` e `DEVICE_NAME`, gera a estrutura padrão do dispositivo e inicia `VirtualIoTDevice`. |
| `device.py` | Gerencia a conexão MQTT, assina o tópico de comandos, publica o handshake, interpreta mensagens recebidas e mantém um worker por sensor. |
| `protocol.py` | Funções puras que montam e interpretam as mensagens do protocolo TATU (JSON compacto e determinístico). |
| `sensor_worker.py` | Uma thread por sensor: coleta valores aleatórios em um intervalo e publica o lote acumulado em outro intervalo. |

---

## Configuração

Toda a configuração é feita por variáveis de ambiente:

| Variável | Padrão | Descrição |
|---|---|---|
| `BROKER_IP` | `127.0.0.1` | Endereço do broker MQTT. |
| `BROKER_PORT` | `1883` | Porta do broker MQTT. |
| `DEVICE_NAME` | UUID aleatório | ID do dispositivo. Define também os tópicos usados. |

### Estrutura padrão do dispositivo

Gerada por `default_device_structure()` em `main.py`:

```json
{
  "id": "<DEVICE_NAME>",
  "latitude": -12.34567890,
  "longitude": 45.67890123,
  "sensors": [
    {"id": "temperatureSensor",   "type": "Thermometer",       "collection_time": 2, "publishing_time": 6},
    {"id": "humiditySensor",      "type": "HumiditySensor",    "collection_time": 2, "publishing_time": 6},
    {"id": "pulseOxymeter",       "type": "PulseOxymeter",     "collection_time": 2, "publishing_time": 6},
    {"id": "windDirectionSensor", "type": "WindDirectionSensor","collection_time": 2, "publishing_time": 6}
  ]
}
```

Latitude e longitude são sorteadas a cada execução. Esse formato espelha o `devices.json` usado pelo gateway.

---

## Como executar

### Localmente

```bash
pip install -r requirements.txt

BROKER_IP=127.0.0.1 BROKER_PORT=1883 DEVICE_NAME=meu-device python -m app.main
```

> O código usa `mqtt.Client(client_id=...)`, que é a API do **paho-mqtt 1.x**. Se o seu `requirements.txt` instalar o paho-mqtt 2.x, será necessário fixar a versão (`paho-mqtt<2.0`) ou passar `mqtt.CallbackAPIVersion.VERSION1` ao criar o cliente.

### Docker

```bash
docker build -t virtual-iot-device .

docker run --rm \
  -e BROKER_IP=host.docker.internal \
  -e BROKER_PORT=1883 \
  -e DEVICE_NAME=meu-device \
  virtual-iot-device
```

Para simular vários dispositivos, basta subir vários containers com `DEVICE_NAME` diferentes (ou sem ele, para receber um UUID).

---

## Tópicos MQTT

| Tópico | Direção | QoS | Uso |
|---|---|---|---|
| `dev/CONNECTIONS` | dispositivo → broker | 1 | Handshake de registro do dispositivo. |
| `dev/{device_id}` | broker → dispositivo | 1 (assinatura) | Comandos `GET` e `FLOW`. |
| `dev/{device_id}/RES` | dispositivo → broker | 1 (GET) / 0 (FLOW) | Respostas e dados dos sensores. |

---

## Protocolo TATU

### 1. Handshake (dispositivo → gateway)

Tópico: `dev/CONNECTIONS`

```
CONNECT VALUE BROKER {"TIME_OUT":10.0,"HEADER":{"NAME":"meu-device"},"DEVICE":{...estrutura...}}
```

O gateway localiza o primeiro `{` da mensagem e faz `json.loads` a partir dali, então o prefixo deve ser exatamente `CONNECT VALUE BROKER `.

### 2. Requisição de leitura única (gateway → dispositivo)

Tópico: `dev/{device_id}`

```
GET VALUE temperatureSensor
```

Resposta em `dev/{device_id}/RES`:

```json
{
  "METHOD": "GET",
  "CODE": "POST",
  "HEADER": {"NAME": "meu-device", "TIMESTAMP": 1712345678901},
  "BODY": {"temperatureSensor": 42.37}
}
```

### 3. Requisição de fluxo (gateway → dispositivo)

Tópico: `dev/{device_id}`

```
FLOW VALUE temperatureSensor {"collect": 2000, "publish": 6000}
```

- `collect`: intervalo de coleta, em **milissegundos**.
- `publish`: intervalo de publicação, em **milissegundos**.
- O `sensor_id` é sempre o terceiro token da mensagem (separada por espaços).

A cada `publish` ms, o dispositivo envia em `dev/{device_id}/RES` todos os valores coletados desde o último envio:

```json
{
  "METHOD": "FLOW",
  "CODE": "POST",
  "HEADER": {"NAME": "meu-device", "TIMESTAMP": 1712345678901},
  "BODY": {
    "temperatureSensor": [12.5, 80.1, 47.9],
    "FLOW": {"collect": 2000, "publish": 6000}
  }
}
```

O campo `BODY.FLOW` é incluído porque o gateway o usa para inferir os timestamps de cada valor do array.

### Mensagens ignoradas

- Payloads vazios.
- Respostas JSON contendo `"METHOD"` que cheguem ao tópico de comandos (por exemplo, um CONNACK do gateway).
- Comandos desconhecidos ou malformados (apenas registrados no log).

---

## Como funcionam os fluxos (`SensorFlowWorker`)

- Existe **um worker (thread daemon) por sensor**, criado na primeira vez que um `FLOW` chega para aquele `sensor_id`.
- A thread roda um loop que, a cada ~10 ms, verifica se já é hora de **coletar** (gera um `float` aleatório entre 0 e 100 com 2 casas decimais e guarda em um buffer) ou de **publicar** (envia o buffer inteiro e o esvazia).
- Se o mesmo sensor receber um novo `FLOW`, os intervalos são **atualizados em tempo real**, sem reiniciar a thread.
- Se o buffer estiver vazio no momento da publicação, nada é enviado.
- Valores com `collect` ou `publish` menores que 1 ms são rejeitados.
- O acesso ao buffer e aos intervalos é protegido por `threading.Lock`.
- Ao encerrar (Ctrl+C), todos os workers são parados e o cliente MQTT é desconectado.

---

## Logs

Todas as ações são impressas na saída padrão com prefixos:

| Prefixo | Significado |
|---|---|
| `[BOOT]` | Inicialização e encerramento. |
| `[MQTT]` | Conexão e assinatura. |
| `[SEND]` | Mensagem publicada. |
| `[RECV]` | Mensagem recebida. |
| `[FLOW]` | Criação, atualização e parada de workers. |
| `[COLLECT]` | Valor coletado por um sensor. |

---

## Limitações conhecidas

- Os valores são **totalmente aleatórios** (0–100), independentemente do tipo do sensor.
- Os campos `collection_time` / `publishing_time` da estrutura do dispositivo (em segundos) **não** disparam fluxos sozinhos; os fluxos só começam quando um comando `FLOW` é recebido.
- Não há comando para **parar** um fluxo individual; os workers só param ao encerrar o dispositivo.
- O handshake é enviado uma única vez na inicialização. Apesar do nome `_publish_handshake_with_retry`, a função apenas aguarda a conexão (até ~3 s) e publica; não há reenvio em caso de falha.
- Os sensores do `GET` e do `FLOW` não são validados contra a lista `sensors` da estrutura: qualquer `sensor_id` é aceito.

---
