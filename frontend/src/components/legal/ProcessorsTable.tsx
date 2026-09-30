import { PROCESSORS } from '@/lib/legal';

/** Recipients table for the privacy policy, rendered from the one list in lib/legal. */
export function ProcessorsTable() {
  return (
    <table>
      <thead>
        <tr>
          <th>Destinatario</th>
          <th>Para qué</th>
          <th>Qué datos</th>
          <th>Dónde</th>
          <th>Garantía</th>
        </tr>
      </thead>
      <tbody>
        {PROCESSORS.map((p) => (
          <tr key={p.name}>
            <td>{p.name}</td>
            <td>{p.purpose}</td>
            <td>{p.data}</td>
            <td>{p.location}</td>
            <td>{p.safeguard}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
