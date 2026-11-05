export type Product = {
  id: string;
  title: string;
  description: string;
  brand: string;
  category: string;
  tags: string[];
};
export type Content = {
  title: string;
  description: string;
  tags: string[];
  citations: string[];
};
export type Citation = {
  id: string;
  text: string;
  document_title: string;
  version: number;
  page: number | null;
  heading: string | null;
};
export type ReviewStatus = "pending_review" | "approved" | "rejected";
export type ReviewAction =
  | "edit"
  | "approve"
  | "reject"
  | "reopen"
  | "regenerate";
export type Proposal = {
  id: string;
  product_id: string;
  batch_id: string;
  original: Product;
  content: Content;
  status: ReviewStatus;
  revision: number;
  is_stale: boolean;
  allowed_actions: ReviewAction[];
  citations?: Citation[];
};
export type Guide = {
  id: string;
  title: string;
  brand: string | null;
  category: string | null;
  version_id: string;
  version: number;
  status: string;
  is_active: boolean;
  error: { code: string; message: string } | null;
};
export type Batch = {
  id: string;
  filename: string;
  status: "pending" | "running" | "completed" | "with_errors";
  total: number;
  finished: number;
  terminal: boolean;
  counts: Record<string, number>;
  dispatch_error: { message: string } | null;
  configuration: { llm_provider: string; embedding_model: string };
};
export type BatchItem = {
  id: string;
  product_id: string;
  original: Product;
  status: string;
  error: { code: string; message: string } | null;
};
