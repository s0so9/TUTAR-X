/// <reference types="vitest/globals" />

/**
 * Vitest TypeScript Declarations
 * 
 * Extend Vitest globals for TypeScript support
 */

import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers'

declare module 'vitest' {
  interface Assertion<T> extends TestingLibraryMatchers<T, void> {}
}
