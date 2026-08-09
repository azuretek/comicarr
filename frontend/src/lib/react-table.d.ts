import "@tanstack/react-table";

import type {
  CellData,
  Row,
  RowData,
  TableFeatures,
} from "@tanstack/react-table";

declare module "@tanstack/react-table" {
  // https://github.com/TanStack/table/issues/44#issuecomment-1377024296
  interface TableMeta<TFeatures extends TableFeatures, TData extends RowData> {
    getRowClassName?: (row: Row<TFeatures, TData>) => string;
    selectAllScope?: "filtered" | "page";
  }

  interface ColumnMeta<
    TFeatures extends TableFeatures,
    TData extends RowData,
    TValue extends CellData = CellData,
  > {
    headerClassName?: string;
    cellClassName?: string;
    label?: string;
  }
}
