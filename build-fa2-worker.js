/**
 * Build script for FA2Layout Web Worker bundle
 *
 * This bundles graphology-layout-forceatlas2/worker for browser use.
 * The CDN version uses CommonJS require() which fails in browsers.
 *
 * Usage: node build-fa2-worker.js
 */

const esbuild = require('esbuild');
const path = require('path');

async function build() {
    try {
        // Bundle the FA2Layout worker for browser
        await esbuild.build({
            entryPoints: ['./fa2-worker-entry.js'],
            bundle: true,
            outfile: './static/js/fa2layout.bundle.js',
            format: 'iife',
            globalName: 'FA2LayoutModule',
            platform: 'browser',
            target: ['es2020'],
            minify: false, // Keep readable for debugging
            sourcemap: true,
            footer: {
                js: '\n// Expose FA2Layout globally\nif (typeof window !== "undefined") { window.FA2Layout = FA2LayoutModule; }\n'
            }
        });

        console.log('✅ FA2Layout bundle created: static/js/fa2layout.bundle.js');
    } catch (error) {
        console.error('❌ Build failed:', error);
        process.exit(1);
    }
}

build();
