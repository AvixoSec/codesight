import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

const TASKS = ['review', 'bugs', 'security', 'docs', 'explain', 'refactor'] as const;
type Task = typeof TASKS[number];

const PROVIDERS = ['openai', 'anthropic', 'google', 'ollama'] as const;
const OUTPUT_FORMATS = ['markdown', 'json', 'plain', 'sarif'] as const;

function pickAllowed<T extends string>(value: string, allowed: readonly T[], fallback: T): T {
    return (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

async function runCodesight(task: Task, filePath: string): Promise<string> {
    const config = vscode.workspace.getConfiguration('codesight');
    const pythonPath = config.get<string>('pythonPath', 'python');
    const provider = pickAllowed(
        config.get<string>('provider', 'openai'),
        PROVIDERS,
        'openai',
    );
    const outputFormat = pickAllowed(
        config.get<string>('outputFormat', 'markdown'),
        OUTPUT_FORMATS,
        'markdown',
    );

    const args = [
        '-m', 'codesight',
        '-p', provider,
        '-o', outputFormat,
        task,
        filePath,
    ];

    const { stdout, stderr } = await execFileAsync(pythonPath, args, {
        maxBuffer: 1024 * 1024 * 10,
        timeout: 120_000,
        shell: false,
    });

    if (stderr && !stdout) {
        throw new Error(stderr);
    }

    return stdout;
}

function createOutputPanel(task: string, filePath: string, content: string): void {
    const panel = vscode.window.createWebviewPanel(
        'codesightResult',
        `CodeSight: ${task}`,
        vscode.ViewColumn.Beside,
        { enableScripts: false },
    );

    const fileName = filePath.split(/[/\\]/).pop() || filePath;

    panel.webview.html = `<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
<style>
    body {
        font-family: var(--vscode-font-family);
        color: var(--vscode-foreground);
        background: var(--vscode-editor-background);
        padding: 20px;
        line-height: 1.6;
    }
    .header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--vscode-widget-border);
    }
    .badge {
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-task {
        background: rgba(139, 92, 246, 0.2);
        color: #c084fc;
    }
    .file {
        color: var(--vscode-descriptionForeground);
        font-size: 13px;
    }
    pre {
        background: var(--vscode-textBlockQuote-background);
        padding: 12px;
        border-radius: 6px;
        overflow-x: auto;
        font-family: var(--vscode-editor-font-family);
        font-size: var(--vscode-editor-font-size);
    }
    h1, h2, h3 { color: var(--vscode-foreground); }
    code {
        font-family: var(--vscode-editor-font-family);
        background: var(--vscode-textBlockQuote-background);
        padding: 2px 5px;
        border-radius: 3px;
    }
</style>
</head>
<body>
    <div class="header">
        <span class="badge badge-task">${escapeHtml(task)}</span>
        <span class="file">${escapeHtml(fileName)}</span>
    </div>
    <div>${escapeHtml(content)}</div>
</body>
</html>`;
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/\n/g, '<br>');
}

async function runAnalysis(task: Task): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('Open a file first.');
        return;
    }

    const filePath = editor.document.uri.fsPath;
    const fileName = filePath.split(/[/\\]/).pop() || filePath;

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: `CodeSight: running ${task} on ${fileName}...`,
            cancellable: false,
        },
        async () => {
            try {
                const result = await runCodesight(task, filePath);
                createOutputPanel(task, filePath, result);
            } catch (err: any) {
                vscode.window.showErrorMessage(`CodeSight error: ${err.message}`);
            }
        },
    );
}

const SAFE_PYTHON_PATH = /^[A-Za-z0-9_./:\\ -]+$/;
const UNSAFE_PATH_CHARS = /[`"'$!|&;<>\r\n]/;

async function scanDirectory(): Promise<void> {
    const uri = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectFiles: false,
        canSelectMany: false,
        openLabel: 'Scan this directory',
    });

    if (!uri || uri.length === 0) { return; }

    const dirPath = uri[0].fsPath;
    if (UNSAFE_PATH_CHARS.test(dirPath)) {
        vscode.window.showErrorMessage(
            'Selected directory path contains characters that are unsafe in a shell context.',
        );
        return;
    }

    const config = vscode.workspace.getConfiguration('codesight');
    const pythonPath = config.get<string>('pythonPath', 'python');
    if (!SAFE_PYTHON_PATH.test(pythonPath)) {
        vscode.window.showErrorMessage(
            'codesight.pythonPath contains unsafe characters; update workspace settings.',
        );
        return;
    }
    const provider = pickAllowed(
        config.get<string>('provider', 'openai'),
        PROVIDERS,
        'openai',
    );

    const scanTasks = ['review', 'bugs', 'security'] as const;
    const picked = await vscode.window.showQuickPick(
        scanTasks as readonly string[],
        { placeHolder: 'Analysis type' },
    );
    if (!picked) { return; }
    const task = pickAllowed(picked, scanTasks, 'review');

    const quote = (s: string): string => s.includes(' ') ? `"${s}"` : s;
    const cmd = [
        quote(pythonPath),
        '-m', 'codesight',
        '-p', provider,
        'scan',
        quote(dirPath),
        '-t', task,
    ].join(' ');

    const terminal = vscode.window.createTerminal('CodeSight Scan');
    terminal.show();
    terminal.sendText(cmd);
}

export function activate(context: vscode.ExtensionContext): void {
    for (const task of TASKS) {
        const disposable = vscode.commands.registerCommand(
            `codesight.${task}`,
            () => runAnalysis(task),
        );
        context.subscriptions.push(disposable);
    }

    context.subscriptions.push(
        vscode.commands.registerCommand('codesight.scanDir', scanDirectory),
    );
}

export function deactivate(): void {}
