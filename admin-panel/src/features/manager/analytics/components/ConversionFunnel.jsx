import { Card, CardHeader, CardBody } from '../../../../components/ui/index.js';
import { FunnelChart } from '../../../../components/domain/index.js';
import { buildFunnelSegments } from '../managerAnalyticsData.js';

/**
 * Tarjeta "Conversión por canal": envuelve el componente de dominio
 * `FunnelChart` con los segmentos derivados de `analytics_funnel`.
 *
 * @param {{ funnel: object|null }} props
 */
export function ConversionFunnel({ funnel }) {
  const segments = buildFunnelSegments(funnel);

  return (
    <Card padding="md">
      <CardHeader
        title="Conversión por canal"
        subtitle="Citas agendadas por canal de captación"
      />
      <CardBody>
        <FunnelChart
          ariaLabel="Conversión por canal"
          segments={segments}
          emptyLabel="Sin datos de funnel en el rango seleccionado."
        />
      </CardBody>
    </Card>
  );
}
