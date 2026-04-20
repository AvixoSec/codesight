import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const TASKS = ['review', 'bugs', 'security', 'docs', 'explain', 'refactor'] as const;
type Task = typeof TASKS[number];

async function runCodesight(task: Task, filePath: string): Promise<string> {
    const config = vscode.workspace.getConfiguration('codesight');
    const pythonPath = config.get<string>('pythonPath', 'python');
    const provider = config.get<string>('provider', 'openai');
    const outputFormat = config.get<string>('outputFormat', 'markdown');

    const cmd = `${pythonPath} -m codesight ${task} "${filePath}" --provider ${provider} -o ${outputFormat}`;

    const { stdout, stderr } = await execAsync(cmd, {
        maxBuffer: 1024 * 1024 * 10,
        timeout: 120_000,
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
        <span class="badge badge-task">${task}</span>
        <span class="file">${fileName}</span>
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

async function scanDirectory(): Promise<void> {
    const uri = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectFiles: false,
        canSelectMany: false,
        openLabel: 'Scan this directory',
    });

    if (!uri || uri.length === 0) { return; }

    const dirPath = uri[0].fsPath;
    const config = vscode.workspace.getConfiguration('codesight');
    const pythonPath = config.get<string>('pythonPath', 'python');
    const provider = config.get<string>('provider', 'openai');

    const task = await vscode.window.showQuickPick(
        ['review', 'bugs', 'security'],
        { placeHolder: 'Analysis type' },
    );
    if (!task) { return; }

    const cmd = `${pythonPath} -m codesight scan "${dirPath}" --task ${task} --provider ${provider}`;

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
