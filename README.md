# ProspectAI Retail Platform

Plataforma demonstrativa de engenharia e análise de dados de varejo, com dados **100% sintéticos**, execução local reproduzível e arquitetura Bronze → Silver → Gold.

## Visão geral

- **Bronze:** guarda cada linha original, sua origem, hash e execução.
- **Silver:** valida esquema, tipos, regras de negócio, referências e atualização mais recente; registros inválidos ficam em quarentena.
- **Gold:** indicadores diários, por categoria e por região. Cada pedido aprovado com pagamento confirmado conta **uma vez**; a receita soma **todos os pagamentos confirmados** desse pedido, sem multiplicar pedidos.
- **Qualidade:** auditoria de execuções, testes de idempotência, integridade referencial e pagamentos múltiplos.
- **CI:** GitHub Actions executa a suíte de testes automaticamente.

## Requisitos

Python 3.11+; nenhuma dependência externa para o pipeline.

## Dados de exemplo no GitHub

A pasta [`data/sample/`](data/sample/) contém quatro CSVs **inteiramente fictícios**, prontos para inspeção e execução: `customers.csv`, `products.csv`, `orders.csv` e `payments.csv`. O diretório mantém o nome `sample` por compatibilidade com o pipeline e o CI, mas agora contém um **dataset representativo de demonstração**, não uma amostra mínima.

O dataset contém **500 clientes, 120 produtos, 5.000 pedidos válidos e 6.106 pagamentos**, cobrindo todo o ano de 2025, múltiplas regiões e categorias, pedidos aprovados, pendentes e cancelados. Inclui **1.106 pedidos com múltiplos pagamentos confirmados** e **um pedido órfão intencional**, enviado à quarentena. Resultado esperado: **3.923 pedidos elegíveis, R$ 5.950.799,70 de receita confirmada e 1 rejeição**. Os valores são sintéticos, não receita real. Os CSVs maiores gerados pelo comando `generate` continuam fora do Git.

Para executar somente a amostra:

```bash
python -m prospectai.pipeline load --input data/sample --db warehouse/sample.db
python -m prospectai.pipeline report --db warehouse/sample.db
python -m prospectai.pipeline export --db warehouse/sample.db --output output/sample-gold
```

## Execução rápida

```bash
python -m prospectai.pipeline generate --output data/synthetic --orders 1000 --seed 42
python -m prospectai.pipeline load --input data/synthetic --db warehouse/retail.db
python -m prospectai.pipeline report --db warehouse/retail.db
python -m prospectai.pipeline export --db warehouse/retail.db --output output/gold
python -m unittest discover -s tests -v
```

Todos os comandos devem ser executados na raiz do repositório. Os três CSVs em `output/gold/` são a fonte de dados preparada para o projeto Power BI. Valores financeiros são expressos em **centavos inteiros**: divida por 100 no modelo de apresentação.

A aba **Actions** executa testes, gera dados, processa Bronze/Silver/Gold, verifica se os totais de pedidos e receitas coincidem nas três dimensões e disponibiliza os arquivos no artefato `prospectai-gold-csv`. A execução só deve ser considerada validada quando o workflow mais recente estiver verde.

## Contrato dos dados

Arquivos CSV: `customers`, `products`, `orders` e `payments`. Cada entidade tem identificador positivo e `updated_at` ISO-8601. Pedidos exigem cliente e produto existentes; pagamentos exigem pedido existente. As entidades são processadas na ordem de dependência, sem apagar histórico Bronze. Valores monetários são armazenados em centavos inteiros para evitar erro de ponto flutuante.

### Política de contabilização

- Somente pedidos `approved` com pelo menos um pagamento `paid` entram nos indicadores Gold.
- `orders`: número de pedidos distintos elegíveis.
- `revenue_cents`: soma dos valores de todos os pagamentos `paid` do pedido (inclusive pagamentos parciais/múltiplos).
- Pagamentos `unpaid` não contribuem; pedidos pendentes/cancelados não contribuem.
- As três dimensões Gold são visões alternativas da mesma receita, não devem ser somadas entre si.

## Qualidade e publicação

O GitHub Actions executa os testes unitários, valida o dataset versionado (incluindo 1.106 pedidos com pagamentos múltiplos, 5.000 pedidos válidos e rejeição de órfãos), processa 1.000 pedidos sintéticos e concilia as três views Gold antes de publicar o artefato `prospectai-gold-csv`. Os CSVs exportados são agregações alternativas; **não some receitas entre arquivos**.

Este projeto é uma demonstração técnica com dados fictícios. O repositório não é um sistema de produção e não contém arquivo `.pbix` pronto. O contrato para o futuro relatório está em [docs/POWER_BI_HANDOFF.md](docs/POWER_BI_HANDOFF.md).

## Estrutura

```text
data/sample/
  customers.csv
  products.csv
  orders.csv
  payments.csv
prospectai/
  __init__.py
  pipeline.py
tests/
  test_pipeline.py
.github/workflows/
  tests.yml
```

## Próximos passos

Conectar um dashboard Power BI às tabelas/views Gold exportadas ou a um warehouse analítico; ampliar observabilidade e implantação conforme requisitos reais. Este repositório não contém dados pessoais, segredos nem integrações de produção.
