# Sistema Autónomo de Recolha de Dados em Ambiente Florestal com Drones

## **Descrição**

Este projeto propõe uma rede autónoma de drones terrestres para recolha e transporte de dados em ambientes florestais sem cobertura de rede celular. A solução é composta por três entidades principais: **base station**, **drones** e **sensores de campo**.

Os sensores recolhem dados ambientais e armazenam-nos localmente. A base station, instalada numa zona com cobertura celular, lança uma frota de drones para missão de exploração.

Os drones percorrem o terreno florestal de forma autónoma, sem qualquer ligação de infraestrutura, comunicando apenas entre si quando estão dentro de alcance. Ao encontrarem sensores (cuja localização é inicialmente desconhecida), recolhem os dados e regressam à base station para os entregar. A base station é então responsável por fazer o upload dos dados para a cloud. A coordenação entre drones é feita através de mensagens **DENM** (*Decentralized Environmental Notification Messages*) para notificação de eventos, e mensagens **CAM** (*Cooperative Awareness Messages*) para consciência situacional.

O sistema inclui ainda lógica de autonomia distribuída, permitindo que os drones tomem decisões locais com base em fatores como posição GPS, sensores já visitados e estado da missão sem depender de conectividade com a base.

---

## **Simulação**

### **Stack de Comunicação: Vanetza-NAP**

A simulação utiliza [Vanetza-NAP](https://github.com/nap-it/vanetza-nap), uma extensão do projeto Vanetza que implementa o protocolo ETSI C-ITS em cima de ITS-G5/IEEE 802.11p. O Vanetza-NAP abstrai toda a codificação/descodificação ASN.1 das mensagens ETSI, expondo uma interface simples via **MQTT** (e opcionalmente DDS/Zenoh) para as aplicações.

Cada contentor executa a imagem `ghcr.io/nap-it/vanetza-nap:latest` e inclui um broker MQTT embutido (`START_EMBEDDED_MOSQUITTO=true`). A aplicação de decisão (lógica do drone, sensor ou base station) corre como um processo separado no mesmo contentor (ou num contentor adjacente), comunicando com o Vanetza-NAP via MQTT local.

### **Interface MQTT com o Vanetza-NAP**

- **Enviar uma mensagem** (ex: CAM ou DENM): publicar o JSON no tópico `vanetza/in/cam` ou `vanetza/in/denm` do broker local.
- **Receber mensagens** de outros nós: subscrever `vanetza/out/cam` ou `vanetza/out/denm`.
- O Vanetza-NAP trata automaticamente da codificação UPER, encapsulamento GeoNetworking/BTP e envio na interface de rede do contentor.
- O campo ITS PDU Header (stationId, etc.) é preenchido automaticamente na codificação; está presente nas mensagens recebidas.

### **Rede Docker e Troca de Mensagens**

- Todos os contentores ligam-se a uma rede Docker partilhada (`vanetzalan0`, subnet `192.168.98.0/24`).
- As mensagens ETSI C-ITS são trocadas diretamente ao nível Ethernet (ethertype `0x8947`) sobre esta rede virtual, tal como aconteceria num canal ITS-G5 real.
- Cada contentor tem um endereço MAC virtual único configurado via `VANETZA_MAC_ADDRESS`.

### **Simulação de Alcance (Out-of-Range)**

A simulação de proximidade — i.e., bloquear comunicação entre nós fora de alcance — é feita via **ebtables** ao nível da camada de ligação (L2), sem qualquer alteração ao código de aplicação:

```bash
# Bloquear comunicação entre dois contentores (ex: drone1 e drone2 saem do alcance)
docker-compose exec drone1 block <MAC_drone2>
docker-compose exec drone2 block <MAC_drone1>

# Restaurar conectividade (voltam ao alcance)
docker-compose exec drone1 unblock <MAC_drone2>
docker-compose exec drone2 unblock <MAC_drone1>
```

O **ProximityManager** (processo externo dedicado) calcula as distâncias entre todos os pares de entidades e emite estes comandos dinamicamente. Esta funcionalidade requer `SUPPORT_MAC_BLOCKING=true` e a capability `NET_ADMIN` no contentor.

### **Configuração dos Contentores**

Os parâmetros de cada entidade são definidos via variáveis de ambiente no `docker-compose.yml`:

| Variável | Descrição |
|---|---|
| `VANETZA_STATION_ID` | ID único da estação ETSI |
| `VANETZA_STATION_TYPE` | Tipo de estação (ex: 15 = unknown) |
| `VANETZA_MAC_ADDRESS` | Endereço MAC virtual |
| `VANETZA_LATITUDE` / `VANETZA_LONGITUDE` | Posição GPS simulada (para nós estáticos) |
| `VANETZA_USE_HARDCODED_GPS` | Usar coordenadas fixas em vez de GPS real |
| `VANETZA_CAM_PERIODICITY` | Periodicidade do CAM automático (ms) |
| `START_EMBEDDED_MOSQUITTO` | Ativar broker MQTT interno |
| `SUPPORT_MAC_BLOCKING` | Ativar suporte a bloqueio MAC via ebtables |

### **Restantes aspetos da simulação**

- **Sensores:** Colocados em posições aleatórias no mapa de simulação, desconhecidas dos drones e da base station. O drone deteta um sensor quando entra no raio de alcançe do mesmo (desbloqueio MAC gerido pelo ProximityManager). Cada sensor corre um processo de aplicação próprio que detém os seus dados ambientais sintéticos e os serve diretamente ao drone via MQTT, sem intervenção de qualquer entidade central.
- **Energia:** A autonomia energética dos drones é ignorada na simulação. Os drones operam sem restrições de bateria.
- **Monitorização:** O dashboard reconstrói o estado da missão exclusivamente a partir do fluxo ETSI — CAMs para posições e DENMs para eventos de cobertura. O ProximityManager publica `sim/links` (matriz de conectividade) e `sim/meta` (configuração do mapa) no broker central para complementar a visualização. As métricas de mensagens (tx/rx por tipo) são expostas via Prometheus (`VANETZA_PROMETHEUS_PORT`).

---

## **Diagrama**

### **Esquema funcional**

```
[ Cloud / Servidor Externo ]
        ↑
        │ upload de dados via rede celular
        │
[ Base Station ] <-- zona com cobertura celular
        ↑
        │ lançamento de missão + receção de dados dos drones
        │ visualização via CAMs recebidos
        ↓
[ Frota de Drones ] --- FANET: CAM + DENM (drone-to-drone, sem infraestrutura)
        ↑
        │  deteção por proximidade + recolha de dados
        ↓
[ Sensores de Campo ] (posição desconhecida, distribuídos aleatoriamente)
```

### **Fluxo da demonstração**

1. Os sensores geram e armazenam dados localmente.
2. A base station lança os drones com a missão de cobrir a área florestal.
3. Cada drone explora autonomamente, usando o algoritmo de cobertura de área.
4. Ao encontrar um sensor, o drone recolhe os dados e emite um **DENM** em broadcast.
5. Outros drones em alcance recebem o DENM e atualizam o seu mapa interno de sensores visitados, evitando recolhas duplicadas.
6. Os drones trocam **CAMs** periodicamente quando em alcance mútuo, partilhando estado (posição, sensores visitados).
7. Quando a missão está concluída, o drone regressa à base station.
8. O drone entrega os dados recolhidos à base station.
9. A base station faz upload para a cloud e reconstrói a visualização da missão.