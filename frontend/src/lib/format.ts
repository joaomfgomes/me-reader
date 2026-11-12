// Formatação de números para mostrar, com as convenções de Portugal.

// Em Portugal os números de quatro algarismos costumam escrever-se sem
// separador ("1468"). Aqui separamos sempre, para as contagens se lerem de
// relance e ficarem alinhadas com as maiores.
const integer = new Intl.NumberFormat("pt-PT", { useGrouping: "always" });
const dollars = new Intl.NumberFormat("pt-PT", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const percent = new Intl.NumberFormat("pt-PT", { style: "percent", maximumFractionDigits: 0 });

/** 161558 passa a "161 558". */
export function formatCount(value: number): string {
  return integer.format(value);
}

/** 2.584928 passa a "2,58 US$". Valores abaixo de um cêntimo não aparecem como zero. */
export function formatUsd(value: number): string {
  // Uma consulta ao tutor custa centésimos de cêntimo. Arredondar para
  // "0,00 US$" daria a entender que foi grátis.
  if (value > 0 && value < 0.01) {
    return `menos de ${dollars.format(0.01)}`;
  }
  return dollars.format(value);
}

/** 0.6667 passa a "67%". */
export function formatPercent(value: number): string {
  return percent.format(value);
}
