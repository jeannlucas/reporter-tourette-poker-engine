# Reporter Tourette Poker Engine

Motor open source de estudo de Texas Hold'em em Python. Calcula equidade
por Monte Carlo, identifica a mão atual, conta outs, mostra pot odds e
sugere uma ação de forma pedagógica — tudo a partir de uma entrada
manual (cartas digitadas ou um print de uma mão já jogada). Vem com CLI,
servidor web local (FastAPI + frontend vanilla) e histórico em SQLite
para revisão.

## Propósito e uso responsável

> Esta é uma ferramenta de **ESTUDO** de Texas Hold'em, para analisar
> mãos e treinar decisões **fora do jogo**. **NÃO é um assistente de
> tempo real (RTA)** e não deve ser usada durante partidas a dinheiro
> real. O uso de softwares de assistência em tempo real viola os termos
> de serviço de salas como **PokerStars** e **Suprema Poker** e pode
> resultar em **banimento e confisco de saldo**. Use para revisar mãos
> depois da sessão e melhorar seu jogo.

Se você não tem certeza se um uso específico está dentro das regras da
sua sala, **não use**. As consequências (banimento, confisco) são
unilaterais e definitivas.

## O que o projeto faz

- **Motor de equidade Monte Carlo**: estima a porcentagem de vitória,
  empate e derrota do herói amostrando mãos do baralho restante para
  os oponentes e completando o board.
- **Identificação de mão atual**: converte (hole + board) para a
  categoria correta (Par, Trinca, Sequência, Flush, Full House, Quadra,
  Straight Flush, Royal Flush), com detecção explícita de Royal Flush.
- **Outs**: conta cartas no baralho remanescente que sobem a categoria
  da mão (par → trinca, par → dois pares, projeto → flush etc.) e
  reporta a equidade aproximada da próxima carta.
- **Pot odds**: calcula equidade requerida e a razão pote:call.
- **Sugestão pedagógica de ação**: compara equidade vs. equidade
  requerida e devolve uma de `FOLD / CHECK / CALL / RAISE`. Heurística
  simples, didática — não é GTO, não considera posição, stack ou fold
  equity.
- **Histórico de mãos**: salva análises em SQLite local, com a ação
  efetivamente tomada e notas — pronto para revisão posterior.
- **OCR opcional**: lê um print de uma mão já jogada via Ollama local
  (modelo de visão) e pré-preenche os campos para você revisar.

## Stack

- **Python 3.9+**
- **FastAPI** + **Uvicorn** — servidor HTTP local
- **treys** — avaliador de mãos de poker (encapsulado atrás de
  `hand_evaluator.py`)
- **SQLite** (módulo `sqlite3` da stdlib) — persistência local
- **Frontend vanilla** — HTML/CSS/JavaScript, sem framework, sem build
- **Ollama** (opcional, externo) — OCR de print via modelo de visão
  `qwen2.5vl`

## Como rodar

### Pré-requisitos

- Python **3.9+**
- Git

### Passos

```bash
# 1. Clone o repositório
git clone <URL_DO_REPO_GITHUB>
cd "Reporter Tourette Poker Engine"

# 2. Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate
# Windows (PowerShell ou cmd):
#   .venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Suba o servidor web
uvicorn reporter_poker.web.server:app --reload
```

Abra <http://127.0.0.1:8000> no navegador. Para usar outra porta:

```bash
uvicorn reporter_poker.web.server:app --port 8765
```

### Rodar os testes

```bash
pytest
```

O teste âncora é
`tests/test_equity.py::test_aa_preflop_heads_up`: AA vs mão aleatória
heads-up tem que convergir para ~85,2% de equidade (tolerância ±1,5%
com 25k iterações e seed fixa).

### CLI alternativa (opcional)

Quem prefere terminal pode usar a CLI interativa:
`python -m reporter_poker.cli`.

## Como usar a interface web

1. Clique nas cartas da grade para preencher, em ordem: as 2 cartas da
   sua mão, o flop (3 cartas), o turn (1) e o river (1). Para remover
   uma carta já posicionada, clique nela no slot.
2. Ajuste **Oponentes**, **Pote**, **Pagar (call)** e **Simulações**.
3. Clique em **Analisar**.

A resposta mostra:

- **Mão atual** (Par, Trinca, Sequência, etc., em PT)
- Barra de **Chance de vitória** + percentuais de empate e derrota
- **Outs** e **Equidade próxima carta**
- **Pot odds** e **Equidade necessária**
- **Ação sugerida** com cor (vermelho = desistir, amarelo = pagar,
  verde = aumentar/apostar, azul = mesa/check)

### API HTTP

`POST /api/analyze` aceita JSON e devolve a análise completa:

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "hole_cards": "As Ad",
    "board": "Kc 7h 2d",
    "num_opponents": 1,
    "pot": 100,
    "to_call": 50,
    "iterations": 25000
  }'
```

Erros de validação (carta inválida, duplicada, board impossível) voltam
como HTTP 400 com a mensagem do motor.

## OCR de print (opcional)

A interface tem um painel **"Ler de imagem (OCR)"** onde você arrasta
ou cola (Ctrl+V) **um print de uma mão que você já jogou** — a ideia é
**evitar redigitar tudo na hora de revisar a mão depois da sessão**.

> Importante: o OCR aqui serve para revisão **pós-jogo**. **Não é, e
> não deve ser usado como, leitura de mesa ao vivo.** Veja a seção
> "Propósito e uso responsável" no topo.

O OCR é **totalmente opcional**. O app funciona 100% com entrada
manual via grid de cartas — você só liga o OCR se quiser.

### Como funciona

A imagem é enviada para uma instância **local** do
[Ollama](https://ollama.com/) rodando o modelo de visão `qwen2.5vl`.
Nada sai da sua máquina, nada é analisado automaticamente: o resultado
do OCR **pré-preenche** os slots, fica destacado em âmbar até você
encostar, e só roda o motor quando você clicar em **Analisar**.

### Pré-requisitos

1. Instale o Ollama: <https://ollama.com/download>.
2. Baixe o modelo de visão (alguns GB — pode demorar):

   ```bash
   ollama pull qwen2.5vl
   ```

3. Deixe o serviço rodando em `http://localhost:11434` (`ollama serve`
   ou o app gráfico — qualquer um dos dois expõe a porta).

### Variáveis de ambiente

| Variável                 | Default                    | Descrição                            |
|--------------------------|----------------------------|--------------------------------------|
| `OLLAMA_HOST`            | `http://localhost:11434`   | Endpoint do Ollama                   |
| `OLLAMA_VISION_MODEL`    | `qwen2.5vl`                | Nome do modelo de visão a usar       |
| `OLLAMA_TIMEOUT_S`       | `90`                       | Timeout HTTP em segundos             |

Exemplo com modelo alternativo:

```bash
OLLAMA_VISION_MODEL=llava uvicorn reporter_poker.web.server:app --reload
```

### Endpoint

`POST /api/ocr` recebe `multipart/form-data` com o campo `image` e
devolve:

```json
{
  "hole_cards": ["As", "Kd"],
  "board": ["Qh", "Jc", "Th"],
  "pot": 200,
  "to_call": 50,
  "num_opponents": 2,
  "warnings": []
}
```

Cartas inválidas detectadas pelo modelo são descartadas e listadas em
`warnings` — a resposta nunca quebra por causa de uma carta mal lida.

Se o Ollama não estiver acessível, o endpoint responde **HTTP 503** com
`"Não foi possível conectar ao Ollama local. Verifique se está
rodando."`. Resposta não-parseável do modelo vira **HTTP 502**.

## Histórico de mãos

A interface tem uma seção **"Histórico de mãos"** abaixo da área de
análise:

1. Você analisa uma mão normalmente.
2. No painel de resultado, clica em **Salvar mão**. Abre um pequeno
   formulário onde você escolhe a **ação tomada** (Desisti / Paguei /
   Aumentei / Mesa / Apostei) e pode digitar uma nota.
3. A mão entra no histórico com o snapshot completo da análise
   (equidade, outs, sugestão, pot odds) e a ação tomada.
4. Por item dá pra **Reabrir** (preenche slots e cenário sem rodar nova
   simulação) ou **Excluir** (confirmação inline, sem alerta de
   browser).

### Persistência

Os dados ficam num arquivo **SQLite local** (sem servidor externo).
Caminho padrão: `./data/history.db`, criado automaticamente. **Esse
arquivo é pessoal** — está no `.gitignore` e não é commitado.

| Variável            | Default              | Descrição                       |
|---------------------|----------------------|---------------------------------|
| `REPORTER_DB_PATH`  | `data/history.db`    | Caminho do arquivo SQLite       |

### Endpoints

| Método  | Rota                | Descrição                                  |
|---------|---------------------|--------------------------------------------|
| POST    | `/api/hands`        | Salva uma mão (snapshot + ação + notas)    |
| GET     | `/api/hands`        | Lista paginada (`?limit=&offset=`)         |
| GET     | `/api/hands/{id}`   | Detalhe de uma mão                          |
| DELETE  | `/api/hands/{id}`   | Remove a mão; 404 se não existir            |

O snapshot salvo inclui campos planos (`suggestion`, `taken_action`,
`is_plus_ev`, `edge_pct`, `win_pct`, `hand_category`, etc.), prontos
para uma futura tela de **estatísticas agregadas** sem reescrever o
schema.

## Arquitetura (resumo)

`GameState` é o contrato central: um dataclass imutável com
`hole_cards`, `board`, `pot`, `to_call` e `num_opponents`. Cinco
módulos consomem ele:

- `hand_evaluator.py` — encapsula `treys`, expõe `HandCategory` (com
  Royal Flush explícito).
- `equity.py` — Monte Carlo e contagem de outs por categoria.
- `pot_odds.py` — equidade requerida, razão e heurística de ação.
- `cli.py` — loop interativo de terminal.
- `web/server.py` — camada de transporte FastAPI; serve a SPA de
  `web/static/`.

Isolar `treys` atrás de `hand_evaluator.py` significa que trocar o
avaliador no futuro mexe em um arquivo só. Mesma ideia para a web: ela
só conhece as funções públicas do motor.

## Limitações

Limites assumidos do MVP — bom de ter em mente ao interpretar a
sugestão:

- **Heurística de ação simples, não-GTO**. Compara equidade bruta com
  pot odds. Não considera posição, profundidade de stack, fold equity
  nem bet sizing.
- **Oponentes recebem mãos aleatórias** do baralho restante — não há
  ranges. Equidade real contra um range apertado costuma ser
  **maior** do que o motor reporta.
- **Outs por categoria de mão**: cartas que aumentam estritamente a
  categoria do herói (par → dois pares, projeto → flush). Não conta
  melhora de kicker nem outs contra um holding específico do vilão.
- **Descrição preflop básica** (pocket pair / suited / offsuit). Não
  classifica em tiers Sklansky ou Chen.

## Licença

[MIT](LICENSE).

## Crédito

Desenvolvido por **BigDev.Z - IT Consulting** —
<https://www.bigdevz.com/>.
