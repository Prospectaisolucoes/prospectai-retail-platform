# Power BI — contrato de dados e início do dashboard

Este documento é o handoff entre o projeto de Engenharia de Dados e o futuro projeto independente de Business Intelligence da ProspectAI.

## Fonte certificada

Baixe o artefato `prospectai-gold-csv` de uma execução **verde** em GitHub Actions. O artefato contém:

| Arquivo | Grão | Colunas |
| --- | --- | --- |
| `gold_daily_sales.csv` | 1 linha por dia com vendas elegíveis | `day`, `orders`, `revenue_cents` |
| `gold_category_sales.csv` | 1 linha por categoria | `category`, `orders`, `revenue_cents` |
| `gold_region_sales.csv` | 1 linha por região | `region`, `orders`, `revenue_cents` |

As três tabelas são **agregações alternativas da mesma população de pedidos**. Não relacione nem some os valores das três entre si; cada visual deve usar a sua própria fonte.

## Regras financeiras

- Um pedido conta uma vez se `status='approved'` e possuir pelo menos um pagamento `paid`.
- Receita é a soma de **todos** os pagamentos confirmados de cada pedido elegível.
- O valor é exportado como inteiro em **centavos**. Converter para reais dividindo por 100.
- Não há estornos, chargebacks, frete, impostos, margem ou devoluções neste conjunto.
- Os dados são fictícios e não devem ser apresentados como resultados comerciais reais.

## Medidas DAX

Depois de importar os três CSVs como tabelas `VendasDia`, `VendasCategoria` e `VendasRegiao`:

```dax
Receita (R$) = DIVIDE(SUM(VendasDia[revenue_cents]), 100)

Pedidos Confirmados = SUM(VendasDia[orders])

Ticket Medio (R$) = DIVIDE([Receita (R$)], [Pedidos Confirmados])

Receita Categoria (R$) = DIVIDE(SUM(VendasCategoria[revenue_cents]), 100)

Pedidos Categoria = SUM(VendasCategoria[orders])

Receita Regiao (R$) = DIVIDE(SUM(VendasRegiao[revenue_cents]), 100)

Pedidos Regiao = SUM(VendasRegiao[orders])
```

As medidas de categoria e região devem ser usadas somente em seus visuais correspondentes. Formate as medidas monetárias como moeda brasileira (R$).

## Layout recomendado para o primeiro dashboard

1. **Resumo comercial:** cartões de Receita, Pedidos e Ticket Médio.
2. **Tendência:** gráfico de linhas por `VendasDia[day]` (converter para Data no Power Query).
3. **Mix de categorias:** barras por `VendasCategoria[category]` com Receita Categoria.
4. **Distribuição regional:** barras por `VendasRegiao[region]` com Receita Região.
5. **Metodologia:** painel com a regra de receita confirmada, natureza sintética dos dados e data de geração.

## Checklist de reconciliação antes de publicar o relatório

Os totais de `orders` e `revenue_cents` precisam ser **iguais** nas três tabelas Gold, antes de aplicar filtros. O workflow do repositório já verifica essa igualdade. Revalide depois da importação no Power BI. Se houver diferença, não publique o dashboard até corrigir a importação ou a modelagem.

## Escopo do projeto de BI

O relatório Power BI será um projeto separado, com seu próprio repositório, screenshots e documentação. Este repositório fornece a origem analítica e o contrato de métricas; não afirma conter um arquivo `.pbix` pronto.
