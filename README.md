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

## Estrutura

```text
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
