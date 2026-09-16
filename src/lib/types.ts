export type MethodStep = { id: string; title: string; body: string };

export type ModelRow = {
  id: string;
  title: string;
  note: string;
  rmsle?: number;
  status: "ok" | "skipped";
  weight?: number;
  org?: string;
  checkpoint?: string;
  error?: string;
  weights?: Record<string, number>;
  top_features?: { feature: string; gain: number }[];
};

export type Point = { date: string; sales?: number; pred?: number };

export type Result = {
  source: string;
  horizon: number;
  n_series: number;
  n_train_rows: number;
  train_end: string;
  test_start: string;
  test_end: string;
  metric: string;
  models: ModelRow[];
  feature_importance: { feature: string; gain: number }[];
  preview: {
    series_id: string;
    history: Point[];
    actual: Point[];
    models: Record<string, Point[]>;
  };
  method: MethodStep[];
  elapsed_sec: number;
  kaggle_ready: boolean;
};

export type Status = { step: string; message: string; pct: number };
