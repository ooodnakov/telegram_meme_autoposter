interface DataTableProps {
  headers: string[];
  rows: (string | number | React.ReactNode)[][];
  emptyMessage?: string;
}

const DataTable = ({ headers, rows, emptyMessage = "No data available." }: DataTableProps) => {
  if (rows.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              {headers.map((header, i) => (
                <th
                  key={i}
                  className="text-left px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-border/50 last:border-0 hover:bg-secondary/30 transition-colors"
              >
                {row.map((cell, j) => (
                  <td key={j} className="px-5 py-3.5 text-sm">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DataTable;
