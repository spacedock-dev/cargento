import * as base from '../observed/generate.test.helper';
import { makeBoards } from '../../test/project_boards';

/* The project differentials' boards and contexts, built from the observed model's own generator. The
   builders live in `frontend/test/project_boards.ts` so the browser proof can use the same ones. */
export const { genBoard, genContext, scenarios, parityBoard } = makeBoards(base);
export type { Scenario } from '../../test/project_boards';
