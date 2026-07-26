# Reporter Tourette Poker Engine

## O que é
Motor open source de estudo de Texas Hold'em em Python. Calcula equidade por
Monte Carlo, identifica a mão atual, conta outs, mostra pot odds e sugere uma
ação de forma pedagógica, a partir de entrada manual (cartas digitadas ou print
de uma mão já jogada). Vem com CLI.

## Modo
MANUTENÇÃO.

Estado em 25/07/2026: existem 10 arquivos de teste em `tests/`. A suíte NÃO foi
executada porque as dependências não estão instaladas (nem `pytest` disponível
no python do sistema). Crie um venv, instale e atualize esta linha com o
resultado real na primeira vez que trabalhar aqui.

## Branches
- Principal: `main`
- Integração: `dev`
- Deploy automático na principal: não se aplica, é biblioteca com CLI.
- Publicar pacote é do Jeann, nunca meu.

## Stack
- Python (dependências em `requirements.txt`)
- Pacote em `reporter_poker/`
- Testes em `tests/`
- Tem `LICENSE`: é o único projeto open source do conjunto.

## Comandos
Não há Makefile nem script declarado. O caminho usual:

- Ambiente: `python3 -m venv .venv && source .venv/bin/activate`
- Instalar: `pip install -r requirements.txt`
- Testes: `pytest tests` (confirmar o runner real ao instalar; pode ser unittest)
- Lint: não existe
- Cobertura: não existe

Confirme os comandos no README antes de assumir, e corrija esta seção se
divergirem.

## Arquitetura real deste projeto
Pacote Python `reporter_poker/` com a lógica, `tests/` espelhando, CLI como
entrada. Sem banco, sem rede, sem interface gráfica: entrada manual e cálculo.

## Desvios conscientes do padrão global
1. **Sem medição de cobertura.** Vale a regra comportamental.
2. **Sem lint configurado.**

## Vocabulário de domínio
- **Equidade**: probabilidade de a mão vencer, aqui estimada por Monte Carlo.
- **Outs**: cartas que ainda podem completar a mão desejada.
- **Pot odds**: relação entre o que se paga e o que se pode ganhar.
- **Texas Hold'em**: variante de pôquer com 2 cartas na mão e 5 comunitárias.

## Armadilhas conhecidas
1. **É repositório PÚBLICO e tem licença open source.** Qualquer coisa
   commitada aqui é visível para qualquer pessoa. Nada de dado pessoal, nada de
   credencial, nem em teste.
2. Cálculo por Monte Carlo é estatístico: teste que compara resultado exato
   tende a ficar instável. Teste de faixa ou com semente fixa é o caminho.
