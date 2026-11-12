import { useQuery } from "@tanstack/react-query";

import { getUsage, type Usage } from "../api/audio";
import { formatCount, formatPercent, formatUsd } from "../lib/format";
import { errorMessage } from "../lib/messages";

// A partir desta fração do teto mensal, a página avisa.
const WARNING_THRESHOLD = 0.8;

/** "2026-11" passa a "novembro de 2026". */
function monthName(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("pt-PT", { month: "long", year: "numeric" }).format(
    new Date(year, monthNumber - 1, 1),
  );
}

export function CostsPage() {
  const usage = useQuery({ queryKey: ["usage"], queryFn: getUsage });

  return (
    <main className="mx-auto min-h-[80vh] w-full max-w-3xl px-5 pt-14 pb-10">
      <h1 className="font-book text-5xl leading-none font-semibold tracking-tight">Custos</h1>

      {usage.isPending && <p className="mt-10 text-pencil">A carregar o consumo…</p>}

      {usage.isError && (
        <p role="alert" className="mt-10 text-danger">
          {errorMessage(usage.error)}
        </p>
      )}

      {usage.data && <VoiceUsage month={usage.data.month} tts={usage.data.tts} />}
    </main>
  );
}

function VoiceUsage({ month, tts }: { month: string; tts: Usage["tts"] }) {
  const used = tts.characters_synthesized;
  const limit = tts.monthly_character_limit;
  const fraction = limit > 0 ? Math.min(1, used / limit) : 1;
  const reached = used >= limit;

  return (
    <section aria-labelledby="voice-heading" className="mt-10 border-t-2 border-ink pt-6">
      <h2 id="voice-heading" className="font-book text-2xl font-semibold">
        Voz em {monthName(month)}
      </h2>

      {reached ? (
        <p role="alert" className="mt-4 border-l-4 border-danger py-1 pl-3 text-danger">
          Atingiste o teto mensal. O áudio já gerado continua a tocar; o resto fica disponível no
          início do próximo mês.
        </p>
      ) : (
        fraction >= WARNING_THRESHOLD && (
          <p role="alert" className="mt-4 border-l-4 border-danger py-1 pl-3">
            Já usaste {formatPercent(fraction)} do teto mensal de voz.
          </p>
        )
      )}

      <p className="mt-6 text-lg">
        <span className="font-book text-4xl font-semibold">{formatCount(used)}</span> de{" "}
        {formatCount(limit)} caracteres enviados ao serviço de voz
      </p>
      {/* <meter> é o elemento nativo para "quanto de um total": os leitores de
          ecrã anunciam o valor sem trabalho extra. */}
      <meter
        className="mt-3 h-3 w-full"
        min={0}
        max={limit}
        value={Math.min(used, limit)}
        aria-label="Parte do teto mensal já usada"
      />
      <p className="mt-1 text-sm text-pencil">
        Faltam {formatCount(tts.characters_remaining)} caracteres para o teto.
      </p>

      <dl className="mt-8 grid gap-x-10 gap-y-5 sm:grid-cols-3">
        <div>
          <dt className="text-sm text-pencil">Custo estimado</dt>
          <dd className="font-book text-2xl font-semibold">{formatUsd(tts.estimated_cost_usd)}</dd>
        </div>
        <div>
          <dt className="text-sm text-pencil">Pedidos servidos pela cache</dt>
          <dd className="font-book text-2xl font-semibold">
            {tts.cache_hit_rate === null ? "Sem pedidos" : formatPercent(tts.cache_hit_rate)}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-pencil">Caracteres poupados pela cache</dt>
          <dd className="font-book text-2xl font-semibold">
            {formatCount(tts.characters_from_cache)}
          </dd>
        </div>
      </dl>

      <p className="mt-8 max-w-prose text-sm text-pencil">
        O custo é uma estimativa feita com o preço configurado na aplicação, não uma fatura. Dentro
        do escalão gratuito do serviço de voz, o valor cobrado é zero. O teto mensal e o preço
        mudam-se no ficheiro .env.
      </p>
    </section>
  );
}
