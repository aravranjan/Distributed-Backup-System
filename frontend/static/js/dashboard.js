// ======================================================
// DISTRIBUTED BACKUP SYSTEM - NETWORK OPERATIONS
// ======================================================

const $ = (id) => document.getElementById(id);

let throughputChart = null;
let recoveryChart = null;
let transferPolling = false;
const serverOnlineState = { h3: false, h4: false };
let activeServerPanel = null;


// ======================================================
// EVENT LOG
// ======================================================

function addEvent(message) {

    const log = $("event-log");

    if (!log) return;

    const entry = document.createElement("div");
    entry.className = "event-entry";

    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = new Date().toLocaleTimeString();

    const text = document.createElement("span");
    text.textContent = message;

    entry.appendChild(time);
    entry.appendChild(text);

    log.prepend(entry);
}


if ($("clear-events")) {

    $("clear-events").addEventListener("click", () => {

        $("event-log").innerHTML = "";

        addEvent("Event log cleared.");
    });
}


// ======================================================
// CLOCK
// ======================================================

function updateClock() {

    if ($("current-time")) {

        $("current-time").textContent =
            new Date().toLocaleString();
    }
}

updateClock();

setInterval(updateClock, 1000);


// ======================================================
// STATUS INDICATORS
// ======================================================

function setStatus(
    dotId,
    textId,
    online,
    onlineText,
    offlineText
) {

    const dot = $(dotId);
    const text = $(textId);

    if (dot) {

        dot.classList.toggle("online", online);
        dot.classList.toggle("offline", !online);
    }

    if (text) {

        text.textContent = online
            ? onlineText
            : offlineText;
    }
}


// ======================================================
// CONTROLLER STATUS
// ======================================================

async function checkController() {

    try {

        const response = await fetch("/api/topology");

        if (!response.ok) {

            throw new Error("Controller unavailable");
        }

        const data = await response.json();

        setStatus(
            "controller-dot",
            "controller-status",
            true,
            "Connected",
            "Disconnected"
        );

        renderTopology(data);

        $("switch-count").textContent =
            (data.switches || []).length;

        $("link-count").textContent =
            (data.links || []).filter(
                link => link.status !== "down"
            ).length;

        $("topology-updated").textContent =
            new Date().toLocaleTimeString();

    } catch (error) {

        setStatus(
            "controller-dot",
            "controller-status",
            false,
            "Connected",
            "Disconnected"
        );

        $("selected-path").textContent =
            "Controller unavailable";

        console.error(error);
    }
}


// ======================================================
// NETWORK TOPOLOGY
// ======================================================

function renderTopology(data) {

    const linksGroup = $("network-links");
    const nodesGroup = $("network-nodes");

    if (!linksGroup || !nodesGroup) return;

    linksGroup.innerHTML = "";
    nodesGroup.innerHTML = "";


    // Fixed topology positions

    const positions = {

        h1: [90, 160],
        h2: [90, 290],

        s1: [340, 225],
        s2: [540, 100],
        s3: [540, 350],
        s4: [750, 225],

        h3: [920, 160],
        h4: [920, 290]
    };


    const switches = (data.switches || []).map(
        id => "s" + id
    );

    const hosts = ["h1", "h2", "h3", "h4"];


    // --------------------------------------------------
    // SELECT THE FORWARDING PATH
    // --------------------------------------------------

    const activePaths = data.active_paths || {};

    let selectedPath = [];

    const targetEntries = Object.values(activePaths);

    const targetEntry = targetEntries.find(
        entry => entry.destination_mac === "00:00:00:00:00:03"
    ) || targetEntries.find(
        entry => entry.destination_mac === "00:00:00:00:00:04"
    );

    const selectedServer =
        targetEntry?.destination_mac === "00:00:00:00:00:04"
            ? "h4"
            : "h3";

    if (targetEntry && targetEntry.path) {

        selectedPath = [
            "h1",
            ...targetEntry.path.map(id => "s" + id),
            selectedServer
        ];
    }


    // --------------------------------------------------
    // DISPLAY COMPLETE FORWARDING PATH
    // --------------------------------------------------

    if (selectedPath.length > 0) {

        $("selected-path").textContent =
            selectedPath.map(node => node.toUpperCase()).join(" → ");

    } else {

        $("selected-path").textContent =
            "Waiting for H1 → backup server forwarding traffic...";
    }


    // --------------------------------------------------
    // DRAW HOST LINKS
    // --------------------------------------------------

    const hostLinks = [

        ["h1", "s1"],
        ["h2", "s1"],
        ["s4", "h3"],
        ["s4", "h4"]
    ];


    hostLinks.forEach(([a, b]) => {

        const selected =
            selectedPath.includes(a) &&
            selectedPath.includes(b);

        let className = "network-link";

        if (selected) {

            className += " selected";
        }

        drawLink(
            linksGroup,
            positions[a],
            positions[b],
            className
        );
    });


    // --------------------------------------------------
    // DRAW SWITCH LINKS
    // --------------------------------------------------

    (data.links || []).forEach(link => {

        const a = "s" + link.source;
        const b = "s" + link.target;

        if (!positions[a] || !positions[b]) return;

        const failed = link.status === "down";

        const indexA = selectedPath.indexOf(a);
        const indexB = selectedPath.indexOf(b);

        const selected =
            indexA !== -1 &&
            indexB !== -1 &&
            Math.abs(indexA - indexB) === 1;

        let className = "network-link";

        if (failed) {

            className += " failed";

        } else if (selected) {

            className += " selected";
        }

        drawLink(
            linksGroup,
            positions[a],
            positions[b],
            className
        );
    });


    // --------------------------------------------------
    // DRAW NETWORK NODES
    // --------------------------------------------------

    [...hosts, ...switches].forEach(name => {

        const position = positions[name];

        if (!position) return;

        const [x, y] = position;

        const isHost = name.startsWith("h");

        const group = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "g"
        );

        const isBackupServer =
            name === "h3" || name === "h4";

        group.setAttribute(
            "class",
            "network-node" + (isBackupServer ? " server" : "")
        );

        group.setAttribute("data-node", name);

        if (isBackupServer) {

            group.setAttribute("tabindex", "0");
            group.setAttribute("role", "button");

            group.setAttribute(
                "aria-label",
                `Open ${name.toUpperCase()} backup server`
            );

            group.addEventListener(
                "click",
                () => openServerPanel(name)
            );

            group.addEventListener("keydown", event => {

                if (event.key === "Enter" || event.key === " ") {

                    event.preventDefault();
                    openServerPanel(name);
                }
            });

            group.classList.add(
                serverOnlineState[name]
                    ? "server-online"
                    : "server-offline"
            );
        }


        const circle = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "circle"
        );

        circle.setAttribute("cx", x);
        circle.setAttribute("cy", y);
        circle.setAttribute("r", isHost ? 25 : 32);

        group.appendChild(circle);


        const label = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "text"
        );

        label.setAttribute("x", x);
        label.setAttribute("y", y + 5);
        label.setAttribute("text-anchor", "middle");

        label.textContent = name.toUpperCase();

        group.appendChild(label);

        nodesGroup.appendChild(group);
    });
}


// ======================================================
// DRAW SVG LINK
// ======================================================

function drawLink(group, start, end, className) {

    const line = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "line"
    );

    line.setAttribute("x1", start[0]);
    line.setAttribute("y1", start[1]);

    line.setAttribute("x2", end[0]);
    line.setAttribute("y2", end[1]);

    line.setAttribute("class", className);

    group.appendChild(line);
}


// ======================================================
// MANUAL TOPOLOGY REFRESH
// ======================================================

if ($("refresh-topology")) {

    $("refresh-topology").addEventListener(
        "click",
        () => {

            checkController();

            addEvent("Network topology refreshed.");
        }
    );
}


// ======================================================
// MININET NETWORK STATUS
// ======================================================

async function checkNetwork() {

    try {

        const response = await fetch("/api/network/status");

        if (!response.ok) {

            throw new Error("Network manager unavailable");
        }

        const data = await response.json();

        setStatus(
            "system-dot",
            "system-status",
            data.running,
            "Network Online",
            "Network Offline"
        );

    } catch (error) {

        setStatus(
            "system-dot",
            "system-status",
            false,
            "Network Online",
            "Manager Unavailable"
        );
    }
}


// ======================================================
// BACKUP SERVER STATUS
// ======================================================

async function checkServers() {

    try {

        const response = await fetch("/api/servers/status");

        if (!response.ok) {

            throw new Error("Server status unavailable");
        }

        const data = await response.json();

        updateServerStatus("h3-status", data.h3);
        updateServerStatus("h4-status", data.h4);

    } catch (error) {

        updateServerStatus("h3-status", false);
        updateServerStatus("h4-status", false);
    }
}


function updateServerStatus(id, online) {

    const element = $(id);

    if (!element) return;

    element.textContent = online ? "Online" : "Offline";

    element.classList.toggle("online", online);
    element.classList.toggle("offline", !online);
    element.classList.remove("unknown");

    const serverName = id.startsWith("h3") ? "h3" : "h4";

    serverOnlineState[serverName] = Boolean(online);

    const node = document.querySelector(
        `[data-node="${serverName}"]`
    );

    if (node) {

        node.classList.toggle("server-online", Boolean(online));
        node.classList.toggle("server-offline", !online);
    }

    const card = document.querySelector(
        `[data-server-card="${serverName}"]`
    );

    if (card) {

        card.setAttribute(
            "aria-label",
            `${serverName.toUpperCase()} backup server, ${online ? "online" : "offline"}. Open controls.`
        );
    }

    if (activeServerPanel === serverName) {

        updateServerModalStatus(serverName, Boolean(online));
    }
}	

// ======================================================
// FILE SELECTION
// ======================================================

if ($("file-input")) {

    $("file-input").addEventListener("change", event => {

        const file = event.target.files[0];

        if (!file) return;

        $("file-details").textContent =
            `${file.name} · ${(file.size / 1048576).toFixed(2)} MiB`;

        $("transfer-message").textContent =
            "Ready to upload.";

        $("transfer-status").textContent = "Ready";

        $("transfer-progress").style.width = "0%";
    });
}


// ======================================================
// FILE UPLOAD
// ======================================================

if ($("upload-form")) {

    $("upload-form").addEventListener(
        "submit",
        async event => {

            event.preventDefault();

            const file = $("file-input").files[0];

            if (!file) {

                addEvent("Please select a file first.");

                return;
            }

            const button = $("upload-button");

            button.disabled = true;
            button.textContent = "Uploading...";

            $("transfer-status").textContent = "Uploading";

            $("transfer-message").textContent =
                "Uploading file to backup system...";

            addEvent(`Uploading ${file.name}`);

            try {

                const formData = new FormData();

                formData.append("file", file);

                const response = await fetch("/api/upload", {

                    method: "POST",

                    body: formData
                });

                const result = await response.json();

                if (!response.ok) {

                    throw new Error(
                        result.error || "Upload failed"
                    );
                }

                addEvent(`File uploaded: ${result.filename}`);

                $("transfer-message").textContent =
                    "Upload complete. Starting TCP backup...";

                await startBackup(result.filename);

            } catch (error) {

                $("transfer-status").textContent = "Failed";

                $("transfer-message").textContent =
                    error.message;

                addEvent("Upload error: " + error.message);

            } finally {

                button.disabled = false;
                button.textContent = "Upload File";
            }
        }
    );
}


// ======================================================
// START BACKUP
// ======================================================

async function startBackup(filename) {

    $("transfer-status").textContent = "Starting";
    $("selected-server").textContent = "Selecting...";
    $("chunk-progress").textContent = "0%";
    $("integrity-status").textContent = "Pending";

    $("transfer-progress").style.width = "0%";

    const response = await fetch("/api/backup/start", {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({

            filename: filename,
            mode: "normal"
        })
    });

    const result = await response.json();

    if (!response.ok) {

        throw new Error(
            result.error || "Could not start backup"
        );
    }

    addEvent(`Backup started for ${filename}`);

    $("transfer-status").textContent = "Running";

    startTransferPolling();
}


// ======================================================
// LIVE TRANSFER PROGRESS
// ======================================================

function startTransferPolling() {

    if (transferPolling) return;

    transferPolling = true;

    pollTransfer();
}


async function pollTransfer() {

    try {

        const response = await fetch("/api/backup/status");

        if (!response.ok) {

            throw new Error("Could not retrieve backup status");
        }

        const data = await response.json();

        const output = data.output || [];

        const combined = output.join("\n");


        // SELECTED SERVER

        const serverMatch = combined.match(
            /Selected server:\s*([\d.]+)/
        );

        if (serverMatch) {

            $("selected-server").textContent =
                serverMatch[1];
        }


        // CHUNK PROGRESS

        const chunks = combined.matchAll(
            /Sent chunk (\d+)\/(\d+)/g
        );

        let current = 0;
        let total = 0;

        for (const match of chunks) {

            current = Number(match[1]);
            total = Number(match[2]);
        }

        if (total > 0) {

            const percentage = Math.round(
                current / total * 100
            );

            $("chunk-progress").textContent =
                `${current}/${total}`;

            $("transfer-progress").style.width =
                `${percentage}%`;
        }


        // AUTOMATIC FAILOVER

        if (combined.includes("INITIATING AUTOMATIC FAILOVER")) {

            $("transfer-status").textContent = "Failover";

            addEvent("Automatic backup server failover initiated.");
        }


        // TRANSFER SUCCESS

        if (combined.includes("TRANSFER SUCCESSFUL")) {

            $("transfer-status").textContent = "Completed";

            $("integrity-status").textContent = "Verified";

            $("transfer-progress").style.width = "100%";

            $("transfer-message").textContent =
                "File transferred successfully. SHA-256 integrity verified.";

            addEvent(
                "Backup successful. File integrity verified."
            );
        }


        // TRANSFER FAILURE

        if (
            combined.includes("TRANSFER CONNECTION FAILED") ||
            combined.includes("TRANSFER FAILED") ||
            (
                data.return_code !== null &&
                data.return_code !== 0 &&
                !data.running
            )
        ) {

            $("transfer-status").textContent = "Failed";

            $("integrity-status").textContent = "Failed";

            $("transfer-message").textContent =
                "Transfer failed. Check the event log.";

            addEvent("Backup transfer failed.");
        }


        // CONTINUE POLLING

        if (data.running) {

            setTimeout(pollTransfer, 700);

        } else {

            transferPolling = false;

            checkServers();
            checkController();
        }

    } catch (error) {

        transferPolling = false;

        $("transfer-message").textContent =
            error.message;

        addEvent(
            "Transfer monitoring error: " + error.message
        );
    }
}


// ======================================================
// PERFORMANCE METRICS
// ======================================================

async function loadMetrics() {

    try {

        const response = await fetch("/api/metrics");

        if (!response.ok) {

            throw new Error("Metrics unavailable");
        }

        const data = await response.json();

        updateMetricCards(data);

        drawCharts(data);

    } catch (error) {

        console.error("Metrics error:", error);
    }
}


function updateMetricCards(data) {

    const throughput = data.throughput || [];
    const recovery = data.recovery || [];


    // AVERAGE THROUGHPUT

    if (throughput.length > 0) {

        const values = throughput.map(
            row => Number(row.Throughput_MiBps)
        ).filter(Number.isFinite);

        if (values.length > 0) {

            const average = values.reduce(
                (sum, value) => sum + value,
                0
            ) / values.length;

            $("throughput").textContent =
                average.toFixed(2);
        }
    }


    // AVERAGE RECOVERY

    if (recovery.length > 0) {

        const values = recovery.map(
            row => Number(row.Recovery_Time_Seconds)
        ).filter(Number.isFinite);

        if (values.length > 0) {

            const average = values.reduce(
                (sum, value) => sum + value,
                0
            ) / values.length;

            $("recovery").textContent =
                (average * 1000).toFixed(2);
        }
    }
}


// ======================================================
// PERFORMANCE CHARTS
// ======================================================

function drawCharts(data) {

    if (typeof Chart === "undefined") return;

    const throughput = data.throughput || [];
    const recovery = data.recovery || [];


    // THROUGHPUT CHART

    const throughputCanvas = $("throughput-chart");

    if (throughputCanvas) {

        if (throughputChart) {

            throughputChart.destroy();
        }

        throughputChart = new Chart(
            throughputCanvas,
            {

                type: "bar",

                data: {

                    labels: throughput.map(
                        row =>
                            `${row.Server} - Trial ${row.Trial}`
                    ),

                    datasets: [{

                        label: "Throughput (MiB/s)",

                        data: throughput.map(
                            row => Number(row.Throughput_MiBps)
                        ),

                        borderWidth: 1
                    }]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {
                            display: false
                        }
                    },

                    scales: {

                        y: {
                            beginAtZero: true
                        }
                    }
                }
            }
        );
    }


    // RECOVERY CHART

    const recoveryCanvas = $("recovery-chart");

    if (recoveryCanvas) {

        if (recoveryChart) {

            recoveryChart.destroy();
        }

        recoveryChart = new Chart(
            recoveryCanvas,
            {

                type: "line",

                data: {

                    labels: recovery.map(
                        row => `Trial ${row.Trial}`
                    ),

                    datasets: [{

                        label: "Recovery Time (ms)",

                        data: recovery.map(
                            row =>
                                Number(row.Recovery_Time_Seconds) * 1000
                        ),

                        tension: 0.3,
                        fill: false
                    }]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    scales: {

                        y: {
                            beginAtZero: true
                        }
                    }
                }
            }
        );
    }
}

// ======================================================
// INITIALIZE DASHBOARD
// ======================================================

async function initializeDashboard() {

    addEvent("Dashboard initialized.");

    initializeServerCards();
    ensureServerModal();

    await checkNetwork();

    await checkController();

    await checkServers();

    await loadMetrics();


    // LIVE STATUS REFRESH

    setInterval(checkController, 3000);

    setInterval(checkNetwork, 3000);

    setInterval(checkServers, 3000);


    // METRICS REFRESH

    setInterval(loadMetrics, 30000);
}


document.addEventListener(
    "DOMContentLoaded",
    initializeDashboard
);


// ======================================================
// INTERACTIVE BACKUP SERVER EXPLORER
// ======================================================

function ensureServerModal() {

    const modal = $("server-modal");

    if (!modal) return null;

    if ($("server-modal-close")) {

        $("server-modal-close").onclick =
            closeServerPanel;
    }

    modal.addEventListener("click", event => {

        if (event.target === modal) {

            closeServerPanel();
        }
    });

    if ($("refresh-server-files")) {

        $("refresh-server-files").onclick = () => {

            if (activeServerPanel) {

                loadServerFiles(activeServerPanel);
            }
        };
    }

    document.addEventListener("keydown", event => {

        if (event.key === "Escape" && !modal.hidden) {

            closeServerPanel();
        }
    });

    return modal;
}


function closeServerPanel() {

    const modal = $("server-modal");

    if (modal) {

        modal.hidden = true;
    }

    activeServerPanel = null;
}


function updateServerModalStatus(server, online) {

    const status = $("server-modal-status");

    if (!status || activeServerPanel !== server) return;

    status.className =
        `server-modal-status ${online ? "online" : "offline"}`;

    status.textContent =
        `${server.toUpperCase()} · ${online ? "ONLINE" : "OFFLINE"}`;
}


async function openServerPanel(server) {

    if (!["h3", "h4"].includes(server)) return;

    const modal = ensureServerModal();

    if (!modal) {

        addEvent("Server explorer panel is missing from the page.");

        return;
    }

    activeServerPanel = server;

    $("server-modal-title").textContent =
        `${server.toUpperCase()} Backup Server`;

    $("server-modal-subtitle").textContent =
        server === "h3"
            ? "10.0.0.3 · Primary backup target"
            : "10.0.0.4 · Secondary backup target";

    modal.hidden = false;

    updateServerModalStatus(
        server,
        Boolean(serverOnlineState[server])
    );

    renderServerActions(
        server,
        Boolean(serverOnlineState[server])
    );

    if (serverOnlineState[server]) {

        await loadServerFiles(server);

    } else {

        $("server-file-list").innerHTML =
            '<p class="empty-files">This server is offline. Start it to inspect stored backups.</p>';
    }

    addEvent(`Opened ${server.toUpperCase()} server panel.`);
}


// ======================================================
// SERVER START / STOP BUTTONS
// ======================================================

function renderServerActions(server, online) {

    const actions = $("server-modal-actions");

    if (!actions) return;

    actions.innerHTML = "";

    const button = document.createElement("button");

    button.type = "button";

    button.className =
        `server-action-button ${online ? "stop" : "start"}`;

    button.textContent =
        online ? "Stop server" : "Start server";

    button.addEventListener(
        "click",
        () => changeServerState(server, online)
    );

    actions.appendChild(button);
}


async function changeServerState(server, currentlyOnline) {

    const actions = $("server-modal-actions");

    const button = actions?.querySelector("button");

    if (button) {

        button.disabled = true;

        button.textContent =
            currentlyOnline ? "Stopping..." : "Starting...";
    }

    try {

        const response = await fetch(
            `/api/servers/${server}/${currentlyOnline ? "stop" : "start"}`,
            {
                method: "POST"
            }
        );

        const result = await response.json();

        if (!response.ok) {

            throw new Error(
                result.error ||
                `Could not ${currentlyOnline ? "stop" : "start"} ${server}`
            );
        }

        addEvent(
            `${server.toUpperCase()} ${currentlyOnline ? "stop" : "start"} request completed.`
        );

        await checkServers();

        const online = Boolean(serverOnlineState[server]);

        renderServerActions(server, online);

        updateServerModalStatus(server, online);

        if (online) {

            await loadServerFiles(server);

        } else {

            $("server-file-list").innerHTML =
                '<p class="empty-files">Server is offline. Stored files remain on disk and will be accessible when it is online.</p>';
        }

    } catch (error) {

        addEvent(
            `Server control error: ${error.message}`
        );

        if (button) {

            button.disabled = false;

            button.textContent =
                currentlyOnline ? "Stop server" : "Start server";
        }
    }
}


// ======================================================
// FILE EXPLORER
// ======================================================

function formatFileSize(bytes) {

    const size = Number(bytes) || 0;

    if (size < 1024) {

        return `${size} B`;
    }

    if (size < 1024 * 1024) {

        return `${(size / 1024).toFixed(1)} KiB`;
    }

    return `${(size / (1024 * 1024)).toFixed(2)} MiB`;
}


async function loadServerFiles(server) {

    if (activeServerPanel !== server) return;

    const list = $("server-file-list");

    list.innerHTML =
        '<p class="empty-files">Loading stored backups...</p>';

    try {

        const response = await fetch(
            `/api/servers/${server}/files`
        );

        const result = await response.json();

        if (!response.ok) {

            throw new Error(
                result.error || "Could not retrieve stored files"
            );
        }

        const files = Array.isArray(result)
            ? result
            : (result.files || []);

        list.innerHTML = "";

        if (files.length === 0) {

            list.innerHTML =
                '<p class="empty-files">No backup files are stored on this server yet.</p>';

            return;
        }

        files.forEach(file => {

            const filename =
                typeof file === "string"
                    ? file
                    : (file.name || file.filename);

            if (!filename) return;

            const size =
                typeof file === "object"
                    ? file.size
                    : 0;

            const row = document.createElement("div");

            row.className = "server-file-row";


            const details = document.createElement("div");

            details.className = "server-file-details";


            const name = document.createElement("div");

            name.className = "server-file-name";

            name.textContent = filename;


            const meta = document.createElement("div");

            meta.className = "server-file-meta";

            meta.textContent = formatFileSize(size);


            details.append(name, meta);


            const download = document.createElement("a");

            download.className = "download-button";

            download.textContent = "Download";

            download.href =
                `/api/servers/${server}/download/${encodeURIComponent(filename)}`;

            download.setAttribute("download", filename);


            row.append(details, download);

            list.appendChild(row);
        });


        if (!list.children.length) {

            list.innerHTML =
                '<p class="empty-files">No downloadable backup files found.</p>';
        }

    } catch (error) {

        list.innerHTML =
            `<p class="empty-files">${escapeHtml(error.message)}</p>`;

        addEvent(
            `${server.toUpperCase()} file listing failed: ${error.message}`
        );
    }
}


// ======================================================
// HTML ESCAPING
// ======================================================

function escapeHtml(value) {

    return String(value).replace(/[&<>"']/g, character => ({

        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"

    })[character]);
}


// ======================================================
// INTERACTIVE SERVER CARDS
// ======================================================

function initializeServerCards() {

    document.querySelectorAll("[data-server-card]").forEach(card => {

        const server = card.dataset.serverCard;

        card.addEventListener(
            "click",
            () => openServerPanel(server)
        );

        card.addEventListener("keydown", event => {

            if (event.key === "Enter" || event.key === " ") {

                event.preventDefault();

                openServerPanel(server);
            }
        });
    });
}


// ======================================================
// NETWORK START / STOP BUTTON
// ======================================================

const networkToggle = document.getElementById("network-toggle");

async function updateNetworkButton() {

    if (!networkToggle) return;

    try {

        const response = await fetch("/api/network/status");
        const data = await response.json();

        networkToggle.textContent = data.running
            ? "Stop Network"
            : "Start Network";

        networkToggle.classList.toggle("danger-button", data.running);
        networkToggle.classList.toggle("primary-button", !data.running);

        networkToggle.disabled = false;

    } catch (error) {

        networkToggle.textContent = "Manager Unavailable";
        networkToggle.disabled = true;
    }
}


if (networkToggle) {

    networkToggle.addEventListener("click", async () => {

        networkToggle.disabled = true;
        networkToggle.textContent = "Please wait...";

        try {

            const statusResponse = await fetch("/api/network/status");
            const status = await statusResponse.json();

            const endpoint = status.running
                ? "/api/network/stop"
                : "/api/network/start";

            const response = await fetch(endpoint, {
                method: "POST"
            });

            const result = await response.json();

            addEvent(
                status.running
                    ? "Network stop requested."
                    : "Network start requested."
            );

            await updateNetworkButton();
            await checkNetwork();
            await checkController();

        } catch (error) {

            addEvent("Network operation failed: " + error.message);

            await updateNetworkButton();
        }
    });

    updateNetworkButton();

    setInterval(updateNetworkButton, 3000);
}
