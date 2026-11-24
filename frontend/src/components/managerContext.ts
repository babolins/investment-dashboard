import { getContext, setContext } from "svelte";
import type { ConfigSummary } from "../types";
import type { TreeNode } from "../lib/hierarchy";

/** Enough to identify a tree node in API calls (names are unique across groups and categories). */
export type NodeRef = Pick<TreeNode, "kind" | "name">;

/** What CategoryManager shares with its recursive rows (so they need no prop threading). */
export interface ManagerContext {
  readonly config: ConfigSummary;
  readonly busy: boolean;
  readonly editing: string | null;
  readonly rowError: { name: string; message: string } | null;
  readonly dragged: NodeRef | null;
  readonly overTarget: string | null;
  /** Group names this node may move to, excluding itself and its descendants. */
  moveTargets(node: NodeRef): string[];
  /** Whether the dragged node may be dropped on a group ("" = top level). */
  canDropOn(target: string): boolean;
  startDrag(node: NodeRef, e: DragEvent): void;
  endDrag(): void;
  dragOver(e: DragEvent, target: string): void;
  dragLeave(e: DragEvent, target: string): void;
  drop(e: DragEvent, target: string): Promise<void>;
  /** Resolves to whether the move succeeded. */
  move(node: NodeRef, parent: string | null): Promise<boolean>;
  remove(node: NodeRef): Promise<void>;
  startEdit(name: string): void;
  cancelEdit(): void;
  fail(name: string, message: string): void;
  save(node: NodeRef, patch: Patch): Promise<void>;
}

export type Patch = { name?: string; buy_symbol?: string; target?: number | null };

const KEY = Symbol("category-manager");

export const provideManager = (ctx: ManagerContext) => setContext(KEY, ctx);
export const useManager = () => getContext<ManagerContext>(KEY);
