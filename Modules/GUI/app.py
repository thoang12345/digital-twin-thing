import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import asdict, is_dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict

from Modules.Digital_Twins.gui_events import parse_dt_gui_event
from Modules.adapters.retrieval_presentation import (
    build_context_chunk_detail_payload,
    build_search_match_detail_payload,
    present_retrieval_content,
    render_detail_text,
)


class AssistantGuiApp:
    POLL_INTERVAL_MS = 100

    def __init__(self, root: tk.Tk, conversation):
        self.root = root
        self.conversation = conversation
        self.event_queue: queue.Queue[Dict[str, Any]] = queue.Queue()

        self.is_busy = False
        self.database_query_busy = False
        self.ingest_busy = False
        self.tool_event_counter = 0

        self.rag_items: Dict[str, Any] = {}
        self.tool_event_items: Dict[str, Dict[str, Any]] = {}
        self.database_items: Dict[str, Dict[str, Any]] = {}
        self.database_query_items: Dict[str, Dict[str, Any]] = {}
        self.available_tool_items: Dict[str, Dict[str, Any]] = {}

        self.status_var = tk.StringVar(value="Ready")
        self.database_status_var = tk.StringVar(
            value="Select a collection and run a direct Chroma query."
        )
        self.ingest_status_var = tk.StringVar(
            value="Choose a target collection, then add text or a file."
        )
        self.summary_finished_var = tk.StringVar(value="n/a")
        self.summary_rounds_var = tk.StringVar(value="0")
        self.summary_rag_var = tk.StringVar(value="0")
        self.summary_tools_var = tk.StringVar(value="0")

        self.selected_collection_var = tk.StringVar(value="")
        self.database_query_var = tk.StringVar(value="")
        self.database_limit_var = tk.IntVar(value=5)

        self.ingest_collection_var = tk.StringVar(value="")
        self.ingest_source_var = tk.StringVar(value="")
        self.ingest_file_path_var = tk.StringVar(value="")
        self.ingest_folder_path_var = tk.StringVar(value="")
        self.ingest_recursive_var = tk.BooleanVar(value=False)

        self._initialize_autonomous_dt_state()

        self._configure_root()
        self._build_layout()
        self._configure_tags()
        self._populate_available_tools()
        self._populate_database_collections()
        self._schedule_queue_poll()

    def _configure_root(self) -> None:
        self.root.title("AI Work V2 Monitor")
        self.root.geometry("1520x960")
        self.root.minsize(1260, 780)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure("Header.TLabel", font=("Segoe UI Semibold", 11))
        style.configure("Status.TLabel", font=("Segoe UI", 10))
        style.configure(
            "DT.LLM.TLabel",
            foreground="#c2410c",
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "DT.Guard.TLabel",
            foreground="#1d4ed8",
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "DT.State.TLabel",
            foreground="#047857",
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "DT.Plant.TLabel",
            foreground="#111827",
            font=("Segoe UI Semibold", 9),
        )
        style.configure("DT.Value.TLabel", font=("Consolas", 10))
        style.configure("DT.Note.TLabel", foreground="#4b5563", font=("Segoe UI", 8))

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.pack(fill="both", expand=True)

        main_pane = ttk.Panedwindow(root_frame, orient="horizontal")
        main_pane.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        right_frame = ttk.Frame(main_pane, padding=(8, 0, 0, 0))
        main_pane.add(left_frame, weight=3)
        main_pane.add(right_frame, weight=2)

        self._build_chat_panel(left_frame)
        self._build_inspector_panel(right_frame)

        status_bar = ttk.Label(
            root_frame,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor="w",
            padding=(4, 8, 4, 0),
        )
        status_bar.pack(fill="x")

    def _build_chat_panel(self, parent: ttk.Frame) -> None:
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(header_frame, text="Chat Loop", style="Header.TLabel").pack(
            side="left"
        )

        controls_frame = ttk.Frame(header_frame)
        controls_frame.pack(side="right")

        self.send_button = ttk.Button(
            controls_frame,
            text="Send",
            command=self._send_query,
        )
        self.send_button.pack(side="right", padx=(8, 0))

        clear_button = ttk.Button(
            controls_frame,
            text="Clear Chat",
            command=self._clear_chat,
        )
        clear_button.pack(side="right")

        self.chat_text = ScrolledText(
            parent,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=30,
        )
        self.chat_text.pack(fill="both", expand=True)

        input_frame = ttk.LabelFrame(parent, text="User Input", padding=8)
        input_frame.pack(fill="x", pady=(10, 0))

        self.input_text = tk.Text(
            input_frame,
            height=5,
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.input_text.pack(fill="x", expand=True)
        self.input_text.bind("<Control-Return>", self._send_query_event)
        self.input_text.bind("<Control-KP_Enter>", self._send_query_event)

        hint = ttk.Label(input_frame, text="Press Ctrl+Enter to send.")
        hint.pack(anchor="e", pady=(6, 0))

    def _build_inspector_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Turn Inspector", style="Header.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        summary_tab = ttk.Frame(notebook, padding=10)
        rag_tab = ttk.Frame(notebook, padding=10)
        tool_tab = ttk.Frame(notebook, padding=10)
        autonomous_dt_tab = ttk.Frame(notebook, padding=10)
        messages_tab = ttk.Frame(notebook, padding=10)

        notebook.add(summary_tab, text="Summary")
        notebook.add(rag_tab, text="RAG")
        notebook.add(tool_tab, text="Tool Loop")
        notebook.add(autonomous_dt_tab, text="Autonomous DT")
        notebook.add(messages_tab, text="Messages")

        self._build_summary_tab(summary_tab)
        self._build_rag_tab(rag_tab)
        self._build_tool_tab(tool_tab)
        self._build_autonomous_dt_tab(autonomous_dt_tab)
        self._build_messages_tab(messages_tab)

    def _build_summary_tab(self, parent: ttk.Frame) -> None:
        stats_frame = ttk.Frame(parent)
        stats_frame.pack(fill="x")

        summary_pairs = [
            ("Finished", self.summary_finished_var),
            ("Rounds", self.summary_rounds_var),
            ("RAG Matches", self.summary_rag_var),
            ("Tool Calls", self.summary_tools_var),
        ]

        for index, (label, variable) in enumerate(summary_pairs):
            box = ttk.LabelFrame(stats_frame, text=label, padding=8)
            box.grid(row=0, column=index, sticky="nsew", padx=(0, 8 if index < 3 else 0))
            stats_frame.columnconfigure(index, weight=1)
            ttk.Label(
                box,
                textvariable=variable,
                font=("Segoe UI Semibold", 12),
            ).pack(anchor="center")

        details_frame = ttk.LabelFrame(parent, text="Turn Details", padding=8)
        details_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.summary_text = ScrolledText(
            details_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.summary_text.pack(fill="both", expand=True)

    def _build_rag_tab(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        current_turn_tab = ttk.Frame(notebook, padding=4)
        database_tab = ttk.Frame(notebook, padding=4)
        ingest_tab = ttk.Frame(notebook, padding=4)
        notebook.add(current_turn_tab, text="Current Turn")
        notebook.add(database_tab, text="Database Browser")
        notebook.add(ingest_tab, text="Ingest")

        self._build_rag_current_turn_tab(current_turn_tab)
        self._build_database_browser_tab(database_tab)
        self._build_ingest_tab(ingest_tab)

    def _build_rag_current_turn_tab(self, parent: ttk.Frame) -> None:
        matches_frame = ttk.LabelFrame(parent, text="Current Turn RAG Matches", padding=8)
        matches_frame.pack(fill="both", expand=True)

        columns = ("source", "score", "preview")
        self.rag_tree = ttk.Treeview(
            matches_frame,
            columns=columns,
            show="headings",
            height=10,
        )
        self.rag_tree.heading("source", text="Source")
        self.rag_tree.heading("score", text="Score")
        self.rag_tree.heading("preview", text="Preview")
        self.rag_tree.column("source", width=160, stretch=True)
        self.rag_tree.column("score", width=80, stretch=False, anchor="center")
        self.rag_tree.column("preview", width=340, stretch=True)
        self.rag_tree.pack(fill="both", expand=True)
        self.rag_tree.bind("<<TreeviewSelect>>", self._on_rag_select)

        details_frame = ttk.LabelFrame(parent, text="Selected RAG Match", padding=8)
        details_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.rag_detail_text = ScrolledText(
            details_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=12,
        )
        self.rag_detail_text.pack(fill="both", expand=True)

    def _build_database_browser_tab(self, parent: ttk.Frame) -> None:
        catalog_frame = ttk.LabelFrame(parent, text="Available Collections", padding=8)
        catalog_frame.pack(fill="both", expand=True)

        catalog_toolbar = ttk.Frame(catalog_frame)
        catalog_toolbar.pack(fill="x", pady=(0, 8))

        ttk.Label(
            catalog_toolbar,
            text="Chroma collections in the current workspace.",
        ).pack(side="left")
        self.database_refresh_button = ttk.Button(
            catalog_toolbar,
            text="Refresh",
            command=self._populate_database_collections,
        )
        self.database_refresh_button.pack(side="right")
        self.database_delete_button = ttk.Button(
            catalog_toolbar,
            text="Delete Selected",
            command=self._delete_selected_collection,
        )
        self.database_delete_button.pack(side="right", padx=(0, 8))
        self.database_clear_button = ttk.Button(
            catalog_toolbar,
            text="Clear Selected",
            command=self._clear_selected_collection,
        )
        self.database_clear_button.pack(side="right", padx=(0, 8))

        self.database_tree = ttk.Treeview(
            catalog_frame,
            columns=("name", "count"),
            show="headings",
            height=6,
        )
        self.database_tree.heading("name", text="Collection")
        self.database_tree.heading("count", text="Count")
        self.database_tree.column("name", width=220, stretch=True)
        self.database_tree.column("count", width=80, stretch=False, anchor="center")
        self.database_tree.pack(fill="both", expand=True)
        self.database_tree.bind("<<TreeviewSelect>>", self._on_database_select)

        query_frame = ttk.LabelFrame(parent, text="Direct Collection Query", padding=8)
        query_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(query_frame, text="Collection").grid(row=0, column=0, sticky="w")
        self.database_collection_combo = ttk.Combobox(
            query_frame,
            textvariable=self.selected_collection_var,
            state="readonly",
            width=26,
        )
        self.database_collection_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(query_frame, text="Top K").grid(row=0, column=1, sticky="w")
        self.database_limit_spinbox = ttk.Spinbox(
            query_frame,
            from_=1,
            to=20,
            textvariable=self.database_limit_var,
            width=6,
        )
        self.database_limit_spinbox.grid(row=1, column=1, sticky="w", padx=(0, 8))

        ttk.Label(query_frame, text="Query").grid(row=0, column=2, sticky="w")
        self.database_query_entry = ttk.Entry(
            query_frame,
            textvariable=self.database_query_var,
        )
        self.database_query_entry.grid(row=1, column=2, sticky="ew", padx=(0, 8))
        self.database_query_entry.bind("<Return>", self._run_database_query_event)

        self.database_query_button = ttk.Button(
            query_frame,
            text="Run Query",
            command=self._run_database_query,
        )
        self.database_query_button.grid(row=1, column=3, sticky="ew")

        query_frame.columnconfigure(0, weight=0)
        query_frame.columnconfigure(1, weight=0)
        query_frame.columnconfigure(2, weight=1)
        query_frame.columnconfigure(3, weight=0)

        ttk.Label(
            query_frame,
            textvariable=self.database_status_var,
            style="Status.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        results_frame = ttk.LabelFrame(parent, text="Direct Query Results", padding=8)
        results_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.database_results_tree = ttk.Treeview(
            results_frame,
            columns=("rank", "id", "score", "preview"),
            show="headings",
            height=8,
        )
        self.database_results_tree.heading("rank", text="#")
        self.database_results_tree.heading("id", text="Document ID")
        self.database_results_tree.heading("score", text="Score")
        self.database_results_tree.heading("preview", text="Preview")
        self.database_results_tree.column("rank", width=45, stretch=False, anchor="center")
        self.database_results_tree.column("id", width=140, stretch=True)
        self.database_results_tree.column("score", width=80, stretch=False, anchor="center")
        self.database_results_tree.column("preview", width=300, stretch=True)
        self.database_results_tree.pack(fill="both", expand=True)
        self.database_results_tree.bind(
            "<<TreeviewSelect>>",
            self._on_database_result_select,
        )

        detail_frame = ttk.LabelFrame(parent, text="Selected Database Result", padding=8)
        detail_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.database_result_detail_text = ScrolledText(
            detail_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=12,
        )
        self.database_result_detail_text.pack(fill="both", expand=True)

    def _build_ingest_tab(self, parent: ttk.Frame) -> None:
        target_frame = ttk.LabelFrame(parent, text="Target Collection", padding=8)
        target_frame.pack(fill="x")

        ttk.Label(target_frame, text="Collection").grid(row=0, column=0, sticky="w")
        self.ingest_collection_combo = ttk.Combobox(
            target_frame,
            textvariable=self.ingest_collection_var,
            state="normal",
            width=28,
        )
        self.ingest_collection_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(target_frame, text="Source Label").grid(row=0, column=1, sticky="w")
        self.ingest_source_entry = ttk.Entry(
            target_frame,
            textvariable=self.ingest_source_var,
        )
        self.ingest_source_entry.grid(row=1, column=1, sticky="ew")

        target_frame.columnconfigure(0, weight=1)
        target_frame.columnconfigure(1, weight=1)

        manual_frame = ttk.LabelFrame(parent, text="Manual Text Entry", padding=8)
        manual_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.ingest_text = ScrolledText(
            manual_frame,
            wrap="word",
            font=("Consolas", 10),
            height=10,
        )
        self.ingest_text.pack(fill="both", expand=True)

        manual_buttons = ttk.Frame(manual_frame)
        manual_buttons.pack(fill="x", pady=(8, 0))
        self.ingest_text_button = ttk.Button(
            manual_buttons,
            text="Add Typed Entry",
            command=self._ingest_text_entry,
        )
        self.ingest_text_button.pack(side="right")

        file_frame = ttk.LabelFrame(parent, text="Document Ingest", padding=8)
        file_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(file_frame, text="Selected File").grid(row=0, column=0, sticky="w")
        self.ingest_file_entry = ttk.Entry(
            file_frame,
            textvariable=self.ingest_file_path_var,
        )
        self.ingest_file_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self.ingest_browse_button = ttk.Button(
            file_frame,
            text="Browse...",
            command=self._choose_ingest_file,
        )
        self.ingest_browse_button.grid(row=1, column=1, padx=(0, 8))

        self.ingest_file_button = ttk.Button(
            file_frame,
            text="Add File",
            command=self._ingest_selected_file,
        )
        self.ingest_file_button.grid(row=1, column=2)

        file_frame.columnconfigure(0, weight=1)

        folder_frame = ttk.LabelFrame(parent, text="Folder Ingest", padding=8)
        folder_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(folder_frame, text="Selected Folder").grid(row=0, column=0, sticky="w")
        self.ingest_folder_entry = ttk.Entry(
            folder_frame,
            textvariable=self.ingest_folder_path_var,
        )
        self.ingest_folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        self.ingest_folder_browse_button = ttk.Button(
            folder_frame,
            text="Browse Folder...",
            command=self._choose_ingest_folder,
        )
        self.ingest_folder_browse_button.grid(row=1, column=1, padx=(0, 8))

        self.ingest_folder_recursive_check = ttk.Checkbutton(
            folder_frame,
            text="Recursive",
            variable=self.ingest_recursive_var,
        )
        self.ingest_folder_recursive_check.grid(row=1, column=2, padx=(0, 8))

        self.ingest_folder_button = ttk.Button(
            folder_frame,
            text="Add Folder",
            command=self._ingest_selected_folder,
        )
        self.ingest_folder_button.grid(row=1, column=3)

        folder_frame.columnconfigure(0, weight=1)

        status_frame = ttk.LabelFrame(parent, text="Ingest Status", padding=8)
        status_frame.pack(fill="both", expand=True, pady=(12, 0))

        ttk.Label(
            status_frame,
            textvariable=self.ingest_status_var,
            style="Status.TLabel",
        ).pack(anchor="w")

        self.ingest_result_text = ScrolledText(
            status_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=10,
        )
        self.ingest_result_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_tool_tab(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        live_tab = ttk.Frame(notebook, padding=4)
        available_tab = ttk.Frame(notebook, padding=4)
        notebook.add(live_tab, text="Live Events")
        notebook.add(available_tab, text="Available Tools")

        self._build_live_tool_tab(live_tab)
        self._build_available_tools_tab(available_tab)

    def _build_live_tool_tab(self, parent: ttk.Frame) -> None:
        self.tool_tree = ttk.Treeview(
            parent,
            columns=("round", "event", "tool", "status"),
            show="headings",
            height=14,
        )
        self.tool_tree.heading("round", text="Round")
        self.tool_tree.heading("event", text="Event")
        self.tool_tree.heading("tool", text="Tool")
        self.tool_tree.heading("status", text="Status")
        self.tool_tree.column("round", width=60, stretch=False, anchor="center")
        self.tool_tree.column("event", width=150, stretch=False)
        self.tool_tree.column("tool", width=180, stretch=True)
        self.tool_tree.column("status", width=100, stretch=False, anchor="center")
        self.tool_tree.pack(fill="both", expand=True)
        self.tool_tree.bind("<<TreeviewSelect>>", self._on_tool_select)

        details_frame = ttk.LabelFrame(parent, text="Selected Tool Event", padding=8)
        details_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.tool_detail_text = ScrolledText(
            details_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=12,
        )
        self.tool_detail_text.pack(fill="both", expand=True)

    def _build_available_tools_tab(self, parent: ttk.Frame) -> None:
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(
            info_frame,
            text="These are the callable tools currently exposed to the agent.",
        ).pack(anchor="w")

        self.available_tools_tree = ttk.Treeview(
            parent,
            columns=("name", "required", "preview"),
            show="headings",
            height=12,
        )
        self.available_tools_tree.heading("name", text="Tool")
        self.available_tools_tree.heading("required", text="Required Fields")
        self.available_tools_tree.heading("preview", text="Description")
        self.available_tools_tree.column("name", width=160, stretch=True)
        self.available_tools_tree.column("required", width=180, stretch=True)
        self.available_tools_tree.column("preview", width=320, stretch=True)
        self.available_tools_tree.pack(fill="both", expand=True)
        self.available_tools_tree.bind(
            "<<TreeviewSelect>>",
            self._on_available_tool_select,
        )

        detail_frame = ttk.LabelFrame(parent, text="Selected Tool Schema", padding=8)
        detail_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.available_tool_detail_text = ScrolledText(
            detail_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=12,
        )
        self.available_tool_detail_text.pack(fill="both", expand=True)

    def _build_messages_tab(self, parent: ttk.Frame) -> None:
        upper = ttk.LabelFrame(parent, text="Initial Messages", padding=8)
        upper.pack(fill="both", expand=True)
        self.initial_messages_text = ScrolledText(
            upper,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=16,
        )
        self.initial_messages_text.pack(fill="both", expand=True)

        lower = ttk.LabelFrame(parent, text="Working Messages", padding=8)
        lower.pack(fill="both", expand=True, pady=(12, 0))
        self.working_messages_text = ScrolledText(
            lower,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
            height=16,
        )
        self.working_messages_text.pack(fill="both", expand=True)

    def _initialize_autonomous_dt_state(self) -> None:
        self.dt_process = None
        self.dt_stop_requested = False

        self.dt_status_var = tk.StringVar(value="No autonomous DT session running.")
        self.dt_supervisor_request_var = tk.StringVar(value="Waiting for decision")
        self.dt_guarded_intent_var = tk.StringVar(value="Waiting for decision")
        self.dt_local_state_var = tk.StringVar(value="Waiting for telemetry")
        self.dt_measured_power_var = tk.StringVar(value="Waiting for telemetry")
        self.dt_telemetry_var = tk.StringVar(value="Waiting for DT telemetry")
        self.dt_adjustment_var = tk.StringVar(
            value="Interface note: no decision received"
        )

        self.dt_backend_var = tk.StringVar(value="udp")
        self.dt_policy_var = tk.StringVar(value="llm")
        self.dt_runner_path_var = tk.StringVar(value=r".\run_dt_runner.py")
        self.dt_model_path_var = tk.StringVar(
            value=r".\Modules\Digital_Twins\DT_enviroment_state_machine_llm_udp.slx"
        )
        self.dt_model_name_var = tk.StringVar(
            value="DT_enviroment_state_machine_llm_udp"
        )

        self.dt_soc_min_var = tk.StringVar(value="40")
        self.dt_soc_max_var = tk.StringVar(value="80")
        self.dt_initial_soc_var = tk.StringVar(value="55")
        self.dt_bus_nominal_var = tk.StringVar(value="400")
        self.dt_tick_seconds_var = tk.StringVar(value="10")
        self.dt_startup_grace_seconds_var = tk.StringVar(value="1")
        self.dt_max_sim_seconds_var = tk.StringVar(value="120")
        self.dt_success_hold_seconds_var = tk.StringVar(value="999")
        self.dt_max_p_batt_var = tk.StringVar(value="480")
        self.dt_max_p_batt_step_var = tk.StringVar(value="100")
        self.dt_real_time_var = tk.BooleanVar(value=False)

        self.dt_csv_path_var = tk.StringVar(value=r".\logs\dt_runner_udp_live.csv")
        self.dt_report_path_var = tk.StringVar(
            value=r".\logs\dt_runner_udp_live_report.md"
        )
        self.dt_llm_log_path_var = tk.StringVar(
            value=r".\logs\dt_runner_udp_live_llm.jsonl"
        )

        self.dt_udp_command_host_var = tk.StringVar(value="127.0.0.1")
        self.dt_udp_command_port_var = tk.StringVar(value="55000")
        self.dt_udp_observation_host_var = tk.StringVar(value="0.0.0.0")
        self.dt_udp_observation_port_var = tk.StringVar(value="55001")
        self.dt_udp_timeout_var = tk.StringVar(value="2")
        self.dt_udp_reset_timeout_var = tk.StringVar(value="5")
        self.dt_udp_command_resend_period_var = tk.StringVar(value="0.25")
        self.dt_udp_send_reset_var = tk.BooleanVar(value=False)
        self.dt_udp_republish_enabled_var = tk.BooleanVar(value=True)
        self.dt_udp_republish_host_var = tk.StringVar(value="127.0.0.1")
        self.dt_udp_republish_port_var = tk.StringVar(value="55002")

        self.dt_llm_base_url_var = tk.StringVar(value="http://127.0.0.1:1234/v1")
        self.dt_llm_model_var = tk.StringVar(value="llama-3-groq-8b-tool-use")
        self.dt_llm_api_key_var = tk.StringVar(value="lm-studio")
        self.dt_llm_temperature_var = tk.StringVar(value="0")
        self.dt_llm_max_tokens_var = tk.StringVar(value="120")
        self.dt_llm_command_limit_var = tk.StringVar(value="480")
        self.dt_llm_verbose_var = tk.BooleanVar(value=True)
        self.dt_llm_strict_var = tk.BooleanVar(value=False)
        self.dt_llm_mode_gate_var = tk.BooleanVar(value=False)
        self.dt_append_llm_log_var = tk.BooleanVar(value=False)

        self.dt_source_min_power_var = tk.StringVar(value="0")
        self.dt_source_power_margin_var = tk.StringVar(value="25")
        self.dt_source_power_limit_var = tk.StringVar(value="500")
        self.dt_allow_source_backfeed_var = tk.BooleanVar(value=False)
        self.dt_allow_charge_without_source_headroom_var = tk.BooleanVar(value=False)
        self.dt_charge_power_margin_var = tk.StringVar(value="25")
        self.dt_charge_bus_hysteresis_volts_var = tk.StringVar(value="5")
        self.dt_charge_recovery_hold_seconds_var = tk.StringVar(value="10")
        self.dt_post_discharge_charge_hold_seconds_var = tk.StringVar(value="10")
        self.dt_allow_discharge_below_soc_min_var = tk.BooleanVar(value=False)
        self.dt_disable_source_support_below_soc_min_var = tk.BooleanVar(value=False)
        self.dt_source_support_entry_margin_var = tk.StringVar(value="5")
        self.dt_source_support_clear_margin_var = tk.StringVar(value="1")
        self.dt_source_support_bus_hysteresis_volts_var = tk.StringVar(value="5")
        self.dt_source_support_hold_seconds_var = tk.StringVar(value="3")
        self.dt_bus_support_min_var = tk.StringVar(value="150")
        self.dt_bus_support_gain_var = tk.StringVar(value="5")
        self.dt_bus_support_integral_gain_var = tk.StringVar(value="0")
        self.dt_bus_support_integral_max_var = tk.StringVar(value="20")
        self.dt_bus_support_integral_leak_var = tk.StringVar(value="0.25")
        self.dt_bus_support_integral_deadband_volts_var = tk.StringVar(value="0.25")
        self.dt_bus_support_trim_gain_var = tk.StringVar(value="0")
        self.dt_bus_support_trim_max_var = tk.StringVar(value="12")
        self.dt_bus_support_trim_decay_var = tk.StringVar(value="0.25")
        self.dt_bus_support_trim_deadband_volts_var = tk.StringVar(value="0.25")
        self.dt_bus_support_trim_source_slack_deadband_var = tk.StringVar(value="2")
        self.dt_bus_support_target_slew_down_var = tk.StringVar(value="0")
        self.dt_safety_recovery_var = tk.BooleanVar(value=False)
        self.dt_safety_recovery_attempts_var = tk.StringVar(value="2")

    def _build_autonomous_dt_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "The agent proposes a supervisory request. The runner validates "
                "the request, while the digital twin's local controller retains "
                "real-time authority. Model-specific settings stay with the "
                "selected runner."
            ),
            wraplength=620,
        ).pack(anchor="w")

        session_frame = ttk.LabelFrame(parent, text="Session", padding=8)
        session_frame.pack(fill="x", pady=(10, 0))

        button_frame = ttk.Frame(session_frame)
        button_frame.pack(side="left")

        self.dt_start_button = ttk.Button(
            button_frame,
            text="Start Session",
            command=self._start_dt_session,
        )
        self.dt_start_button.pack(side="left")

        self.dt_stop_button = ttk.Button(
            button_frame,
            text="Stop",
            command=self._stop_dt_session,
        )
        self.dt_stop_button.pack(side="left", padx=(8, 0))

        self.dt_copy_command_button = ttk.Button(
            button_frame,
            text="Copy Command",
            command=self._copy_dt_command,
        )
        self.dt_copy_command_button.pack(side="left", padx=(8, 0))

        self.dt_open_report_button = ttk.Button(
            button_frame,
            text="Open Report",
            command=self._open_dt_report,
        )
        self.dt_open_report_button.pack(side="left", padx=(8, 0))

        ttk.Label(
            session_frame,
            textvariable=self.dt_status_var,
            style="Status.TLabel",
        ).pack(side="left", padx=(14, 0), fill="x", expand=True)

        self._build_dt_authority_display(parent)

        settings_notebook = ttk.Notebook(parent, height=235)
        self.dt_settings_notebook = settings_notebook
        settings_notebook.pack(fill="x", pady=(10, 0))

        run_tab = ttk.Frame(settings_notebook, padding=8)
        model_tab = ttk.Frame(settings_notebook, padding=8)
        connection_tab = ttk.Frame(settings_notebook, padding=8)
        agent_tab = ttk.Frame(settings_notebook, padding=8)
        settings_notebook.add(run_tab, text="Run")
        settings_notebook.add(model_tab, text="Model Inputs")
        settings_notebook.add(connection_tab, text="Connection")
        settings_notebook.add(agent_tab, text="Agent")

        self._build_dt_run_settings(self._build_dt_scrollable_settings_tab(run_tab))
        self._build_dt_model_inputs(
            self._build_dt_scrollable_settings_tab(model_tab)
        )
        self._build_dt_udp_settings(
            self._build_dt_scrollable_settings_tab(connection_tab)
        )
        self._build_dt_llm_settings(
            self._build_dt_scrollable_settings_tab(agent_tab)
        )

        command_frame = ttk.LabelFrame(parent, text="Command Preview", padding=8)
        command_frame.pack(fill="x", pady=(10, 0))
        self.dt_command_preview_text = ScrolledText(
            command_frame,
            wrap="word",
            font=("Consolas", 9),
            height=2,
            state="disabled",
        )
        self.dt_command_preview_text.pack(fill="x")

        output_frame = ttk.LabelFrame(parent, text="Live Runner Output", padding=8)
        output_frame.pack(fill="both", expand=True, pady=(10, 0))

        output_toolbar = ttk.Frame(output_frame)
        output_toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(
            output_toolbar,
            text="Clear Output",
            command=lambda: self._set_text_widget(self.dt_output_text, ""),
        ).pack(side="right")

        self.dt_output_text = ScrolledText(
            output_frame,
            wrap="word",
            font=("Consolas", 9),
            height=5,
            state="disabled",
        )
        self.dt_output_text.pack(fill="both", expand=True)

        self._refresh_dt_command_preview()
        self._set_dt_running(False)

    def _build_dt_authority_display(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Live Control Path", padding=8)
        self.dt_authority_frame = frame
        frame.pack(fill="x", pady=(10, 0))

        stages = (
            (
                "1  AGENT REQUEST",
                self.dt_supervisor_request_var,
                "Supervisory decision",
                "DT.LLM.TLabel",
            ),
            (
                "2  RUNNER OUTPUT",
                self.dt_guarded_intent_var,
                "Validated interface command",
                "DT.Guard.TLabel",
            ),
            (
                "3  LOCAL CONTROL",
                self.dt_local_state_var,
                "State reported by the DT",
                "DT.State.TLabel",
            ),
            (
                "4  DT FEEDBACK",
                self.dt_measured_power_var,
                "Model-specific measured output",
                "DT.Plant.TLabel",
            ),
        )
        for column, (title, variable, note, style) in enumerate(stages):
            stage = ttk.Frame(frame, padding=(6, 2))
            stage.grid(row=0, column=column, sticky="nsew", padx=(0, 6))
            ttk.Label(stage, text=title, style=style).pack(anchor="w")
            ttk.Label(
                stage,
                textvariable=variable,
                style="DT.Value.TLabel",
                wraplength=145,
            ).pack(anchor="w", pady=(4, 0))
            ttk.Label(
                stage,
                text=note,
                style="DT.Note.TLabel",
                wraplength=145,
            ).pack(anchor="w", pady=(3, 0))
            frame.columnconfigure(column, weight=1)

        ttk.Separator(frame, orient="horizontal").grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(6, 4),
        )
        ttk.Label(
            frame,
            textvariable=self.dt_telemetry_var,
            style="DT.Value.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            textvariable=self.dt_adjustment_var,
            style="DT.Note.TLabel",
            wraplength=320,
        ).grid(row=2, column=2, columnspan=2, sticky="e")

    def _build_dt_scrollable_settings_tab(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=8)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event) -> None:
            canvas.itemconfigure(content_window, width=event.width)

        def scroll_with_wheel(event) -> str:
            canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        canvas.bind("<MouseWheel>", scroll_with_wheel)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        return content

    def _build_dt_run_settings(self, parent: ttk.Frame) -> None:
        mode_frame = ttk.LabelFrame(parent, text="Runner", padding=8)
        mode_frame.pack(fill="x")

        ttk.Label(mode_frame, text="Backend").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            mode_frame,
            textvariable=self.dt_backend_var,
            values=("udp", "simulink", "mock"),
            state="readonly",
            width=16,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(mode_frame, text="Agent policy").grid(
            row=0,
            column=1,
            sticky="w",
        )
        ttk.Combobox(
            mode_frame,
            textvariable=self.dt_policy_var,
            values=("llm", "heuristic"),
            state="readonly",
            width=16,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Checkbutton(
            mode_frame,
            text="Real-time pacing",
            variable=self.dt_real_time_var,
        ).grid(row=1, column=2, sticky="w")
        for column in range(3):
            mode_frame.columnconfigure(column, weight=1)

        timing_frame = ttk.LabelFrame(parent, text="Timing", padding=8)
        timing_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            timing_frame,
            [
                ("Agent tick seconds", self.dt_tick_seconds_var),
                ("Startup grace seconds", self.dt_startup_grace_seconds_var),
                ("Maximum simulation seconds", self.dt_max_sim_seconds_var),
                ("Success hold seconds", self.dt_success_hold_seconds_var),
            ],
            columns=2,
        )

        artifacts_frame = ttk.LabelFrame(parent, text="Artifacts", padding=8)
        artifacts_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            artifacts_frame,
            [
                ("CSV event log", self.dt_csv_path_var),
                ("Markdown report", self.dt_report_path_var),
            ],
            columns=2,
        )

    def _build_dt_model_inputs(self, parent: ttk.Frame) -> None:
        selection_frame = ttk.LabelFrame(parent, text="Digital Twin", padding=8)
        selection_frame.pack(fill="x")
        self._build_dt_path_row(
            selection_frame,
            0,
            "Runner script",
            self.dt_runner_path_var,
            self._choose_dt_runner_path,
        )
        self._build_dt_path_row(
            selection_frame,
            2,
            "Model file",
            self.dt_model_path_var,
            self._choose_dt_model_path,
        )
        self._build_dt_settings_grid(
            selection_frame,
            [("Model identifier", self.dt_model_name_var)],
            columns=1,
            start_row=4,
        )

        inputs_frame = ttk.LabelFrame(
            parent,
            text="DT-Specific Runner Arguments",
            padding=8,
        )
        inputs_frame.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(
            inputs_frame,
            text=(
                "Use one command-line option per line. These inputs belong to "
                "the selected DT runner and can be replaced for another model."
            ),
            wraplength=590,
        ).pack(anchor="w")
        self.dt_model_inputs_text = tk.Text(
            inputs_frame,
            height=6,
            wrap="none",
            font=("Consolas", 9),
        )
        self.dt_model_inputs_text.pack(fill="both", expand=True, pady=(6, 0))
        self.dt_model_inputs_text.insert(
            "1.0",
            "\n".join(
                (
                    "--soc-min 40",
                    "--soc-max 80",
                    "--initial-soc 55",
                    "--bus-nominal 400",
                    "--max-p-batt 480",
                    "--max-p-batt-step 100",
                    "--source-power-limit 500",
                    "--llm-command-limit 480",
                )
            ),
        )
        ttk.Label(
            inputs_frame,
            text=(
                "The GUI does not interpret these values. The runner defines "
                "their meaning and the model owns its local control logic."
            ),
            style="DT.Note.TLabel",
            wraplength=590,
        ).pack(anchor="w", pady=(6, 0))

    def _build_dt_mission_settings(self, parent: ttk.Frame) -> None:
        mode_frame = ttk.LabelFrame(parent, text="Supervisor and Backend", padding=8)
        mode_frame.pack(fill="x")

        ttk.Label(mode_frame, text="Backend").grid(row=0, column=0, sticky="w")
        self.dt_backend_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.dt_backend_var,
            values=("udp", "simulink", "mock"),
            state="readonly",
            width=16,
        )
        self.dt_backend_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(mode_frame, text="Supervisor policy").grid(
            row=0,
            column=1,
            sticky="w",
        )
        self.dt_policy_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.dt_policy_var,
            values=("llm", "heuristic"),
            state="readonly",
            width=16,
        )
        self.dt_policy_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        self.dt_real_time_check = ttk.Checkbutton(
            mode_frame,
            text="Real-time sleeps between ticks",
            variable=self.dt_real_time_var,
        )
        self.dt_real_time_check.grid(row=1, column=2, sticky="w")
        for column in range(3):
            mode_frame.columnconfigure(column, weight=1)

        timing_frame = ttk.LabelFrame(
            parent,
            text="Supervisory Timing and Request Limits",
            padding=8,
        )
        timing_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            timing_frame,
            [
                ("Supervisor tick seconds", self.dt_tick_seconds_var),
                ("Startup grace seconds", self.dt_startup_grace_seconds_var),
                ("Max sim seconds", self.dt_max_sim_seconds_var),
                ("Success hold seconds", self.dt_success_hold_seconds_var),
                ("SOC min %", self.dt_soc_min_var),
                ("SOC max %", self.dt_soc_max_var),
                ("Initial SOC % (mock)", self.dt_initial_soc_var),
                ("Bus nominal V", self.dt_bus_nominal_var),
                ("Max guarded request W", self.dt_max_p_batt_var),
                ("Max request step W", self.dt_max_p_batt_step_var),
            ],
            columns=2,
        )

        model_frame = ttk.LabelFrame(
            parent,
            text="State-Machine Model Reference and Artifacts",
            padding=8,
        )
        model_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_path_row(
            model_frame,
            0,
            "Simulink state-machine model path",
            self.dt_model_path_var,
            self._choose_dt_model_path,
        )
        self._build_dt_settings_grid(
            model_frame,
            [("Model name", self.dt_model_name_var)],
            columns=1,
            start_row=2,
        )
        self._build_dt_path_row(
            model_frame,
            4,
            "CSV audit log",
            self.dt_csv_path_var,
            lambda: self._choose_dt_save_path(
                self.dt_csv_path_var,
                "Choose CSV audit log path",
                ".csv",
                [("CSV files", "*.csv"), ("All files", "*.*")],
            ),
        )
        ttk.Label(
            model_frame,
            text=(
                "UDP mode expects this model to be running separately; the path "
                "identifies the intended controller but the Python runner does not "
                "open Simulink."
            ),
            style="DT.Note.TLabel",
            wraplength=590,
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._build_dt_path_row(
            model_frame,
            6,
            "Markdown report",
            self.dt_report_path_var,
            lambda: self._choose_dt_save_path(
                self.dt_report_path_var,
                "Choose mission report path",
                ".md",
                [("Markdown files", "*.md"), ("All files", "*.*")],
            ),
        )
        self._build_dt_path_row(
            model_frame,
            8,
            "LLM JSONL trace",
            self.dt_llm_log_path_var,
            lambda: self._choose_dt_save_path(
                self.dt_llm_log_path_var,
                "Choose LLM trace log path",
                ".jsonl",
                [("JSONL files", "*.jsonl"), ("All files", "*.*")],
            ),
        )

    def _build_dt_udp_settings(self, parent: ttk.Frame) -> None:
        network_frame = ttk.LabelFrame(parent, text="UDP Network", padding=8)
        network_frame.pack(fill="x")
        self._build_dt_settings_grid(
            network_frame,
            [
                ("Command host", self.dt_udp_command_host_var),
                ("Command port", self.dt_udp_command_port_var),
                ("Observation host", self.dt_udp_observation_host_var),
                ("Observation port", self.dt_udp_observation_port_var),
                ("Observation timeout seconds", self.dt_udp_timeout_var),
                ("Reset timeout seconds", self.dt_udp_reset_timeout_var),
                ("Command resend period seconds", self.dt_udp_command_resend_period_var),
            ],
            columns=2,
        )

        options_frame = ttk.LabelFrame(parent, text="UDP Options", padding=8)
        options_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            options_frame,
            text="Send reset packet before waiting for telemetry",
            variable=self.dt_udp_send_reset_var,
        ).grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Checkbutton(
            options_frame,
            text="Republish received observations",
            variable=self.dt_udp_republish_enabled_var,
        ).grid(row=1, column=0, sticky="w", columnspan=2, pady=(6, 0))
        self._build_dt_settings_grid(
            options_frame,
            [
                ("Republish host", self.dt_udp_republish_host_var),
                ("Republish port", self.dt_udp_republish_port_var),
            ],
            columns=2,
            start_row=2,
        )

    def _build_dt_llm_settings(self, parent: ttk.Frame) -> None:
        connection_frame = ttk.LabelFrame(
            parent,
            text="OpenAI-Compatible Agent Endpoint",
            padding=8,
        )
        connection_frame.pack(fill="x")
        self._build_dt_settings_grid(
            connection_frame,
            [
                ("Base URL", self.dt_llm_base_url_var),
                ("Model", self.dt_llm_model_var),
                ("API key", self.dt_llm_api_key_var),
                ("Temperature", self.dt_llm_temperature_var),
                ("Max tokens", self.dt_llm_max_tokens_var),
            ],
            columns=2,
        )

        options_frame = ttk.LabelFrame(
            parent,
            text="LLM Supervisory Request Options",
            padding=8,
        )
        options_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            options_frame,
            text="Verbose console request/response logging",
            variable=self.dt_llm_verbose_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options_frame,
            text="Strict mode: stop runner instead of using fallback intent",
            variable=self.dt_llm_strict_var,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            options_frame,
            text="Append to existing LLM trace instead of resetting it",
            variable=self.dt_append_llm_log_var,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        trace_frame = ttk.LabelFrame(parent, text="Agent Trace", padding=8)
        trace_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            trace_frame,
            [("JSONL request/response log", self.dt_llm_log_path_var)],
            columns=1,
        )

    def _build_dt_state_controller_reference(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "Read-only reference for the controller implemented inside "
                "DT_enviroment_state_machine_llm_udp.slx. The LLM cannot "
                "select these states directly or bypass their transition guards."
            ),
            wraplength=620,
        ).pack(anchor="w")

        state_frame = ttk.LabelFrame(
            parent,
            text="Local States and Battery-Power Outputs",
            padding=8,
        )
        state_frame.pack(fill="x", pady=(10, 0))
        state_tree = ttk.Treeview(
            state_frame,
            columns=("state", "code", "output", "purpose"),
            show="headings",
            height=4,
        )
        self.dt_state_controller_tree = state_tree
        for column, heading, width in (
            ("state", "State", 90),
            ("code", "Code", 40),
            ("output", "Controller output", 140),
            ("purpose", "Purpose", 230),
        ):
            state_tree.heading(column, text=heading)
            state_tree.column(column, width=width, minwidth=width, stretch=True)
        for values in (
            ("SAFE_LOCAL", "3", "0 W", "Fail closed on invalid or unsafe input"),
            (
                "BUS_SUPPORT",
                "2",
                "0 to +480 W",
                "Local deficit/voltage control; feasible discharge intent",
            ),
            (
                "CHARGE",
                "1",
                "0 to -300 W",
                "Charge request limited by source headroom",
            ),
            ("HOLD", "0", "0 W", "Neutral default"),
        ):
            state_tree.insert("", "end", values=values)
        state_tree.pack(fill="x")

        thresholds_frame = ttk.LabelFrame(
            parent,
            text="Implemented Transition Guards",
            padding=8,
        )
        thresholds_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(
            thresholds_frame,
            text=(
                "Priority: safety > bus support > charge > hold.\n"
                "Bus support: enter at Vbus <= 397 V, source limit, nominal load "
                ">= 475 W, or DISCHARGE request; clear at Vbus >= 399 V, source "
                "clear, nominal load <= 465 W, and no DISCHARGE request.\n"
                "Charge: enter only for CHARGE request, SOC < 39.9%, headroom > 1 W, "
                "and Vbus >= 399 V; abort to support at Vbus <= 395 V.\n"
                "Hard local safety: invalid telemetry, SOC <= 10% or >= 95%, or "
                "Vbus <= 250 V or >= 500 V."
            ),
            wraplength=620,
            justify="left",
        ).pack(anchor="w")

        ttk.Label(
            parent,
            text=(
                "Positive battery power discharges into the bus; negative power "
                "charges the battery. Edit the Simulink build script—not the LLM "
                "prompt—to change local controller thresholds."
            ),
            style="DT.Note.TLabel",
            wraplength=620,
        ).pack(anchor="w", pady=(8, 0))

    def _build_dt_guard_settings(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "These settings constrain the supervisor request in Python before "
                "UDP transmission. They do not replace or retune the local Simulink "
                "state controller shown on the adjacent tab."
            ),
            wraplength=620,
        ).pack(anchor="w")

        source_frame = ttk.LabelFrame(
            parent,
            text="Python Source and Charge Guard",
            padding=8,
        )
        source_frame.pack(fill="x")
        self._build_dt_settings_grid(
            source_frame,
            [
                ("Source min power W", self.dt_source_min_power_var),
                ("Source power margin W", self.dt_source_power_margin_var),
                ("Source power limit W", self.dt_source_power_limit_var),
                ("Charge power margin W", self.dt_charge_power_margin_var),
                ("Charge bus hysteresis V", self.dt_charge_bus_hysteresis_volts_var),
                ("Charge recovery hold seconds", self.dt_charge_recovery_hold_seconds_var),
                (
                    "Post-discharge charge hold seconds",
                    self.dt_post_discharge_charge_hold_seconds_var,
                ),
            ],
            columns=2,
        )

        guard_flags_frame = ttk.LabelFrame(
            parent,
            text="Python Guard Overrides",
            padding=8,
        )
        guard_flags_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            guard_flags_frame,
            text="Allow source backfeed",
            variable=self.dt_allow_source_backfeed_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            guard_flags_frame,
            text="Allow charging without source headroom telemetry",
            variable=self.dt_allow_charge_without_source_headroom_var,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            guard_flags_frame,
            text="Allow discretionary discharge below SOC minimum",
            variable=self.dt_allow_discharge_below_soc_min_var,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(
            guard_flags_frame,
            text="Disable low-SOC source-support exception",
            variable=self.dt_disable_source_support_below_soc_min_var,
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))

        recovery_frame = ttk.LabelFrame(
            parent,
            text="Runner Safety Recovery",
            padding=8,
        )
        recovery_frame.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            recovery_frame,
            text="LLM recovery pass before full safe stop for recoverable hard violations",
            variable=self.dt_safety_recovery_var,
        ).grid(row=0, column=0, sticky="w", columnspan=2)
        self._build_dt_settings_grid(
            recovery_frame,
            [("Max recovery attempts", self.dt_safety_recovery_attempts_var)],
            columns=1,
            start_row=1,
        )

        source_support_frame = ttk.LabelFrame(
            parent,
            text="Advanced Python Source-Support Latch",
            padding=8,
        )
        source_support_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            source_support_frame,
            [
                ("Entry margin W", self.dt_source_support_entry_margin_var),
                ("Clear margin W", self.dt_source_support_clear_margin_var),
                ("Bus hysteresis V", self.dt_source_support_bus_hysteresis_volts_var),
                ("Hold seconds", self.dt_source_support_hold_seconds_var),
            ],
            columns=2,
        )

        bus_support_frame = ttk.LabelFrame(
            parent,
            text="Advanced Python Bus-Support Proposal",
            padding=8,
        )
        bus_support_frame.pack(fill="x", pady=(10, 0))
        self._build_dt_settings_grid(
            bus_support_frame,
            [
                ("Minimum support W", self.dt_bus_support_min_var),
                ("Gain W/V", self.dt_bus_support_gain_var),
                ("Integral gain W/V/s", self.dt_bus_support_integral_gain_var),
                ("Integral max W", self.dt_bus_support_integral_max_var),
                ("Integral leak 1/s", self.dt_bus_support_integral_leak_var),
                (
                    "Integral deadband V",
                    self.dt_bus_support_integral_deadband_volts_var,
                ),
                ("Trim gain W/V/s", self.dt_bus_support_trim_gain_var),
                ("Trim max W", self.dt_bus_support_trim_max_var),
                ("Trim decay W/s", self.dt_bus_support_trim_decay_var),
                ("Trim deadband V", self.dt_bus_support_trim_deadband_volts_var),
                (
                    "Trim source slack deadband W",
                    self.dt_bus_support_trim_source_slack_deadband_var,
                ),
                ("Target slew down W/s", self.dt_bus_support_target_slew_down_var),
            ],
            columns=2,
        )

    def _build_dt_settings_grid(
        self,
        parent,
        fields,
        columns: int,
        start_row: int = 0,
    ) -> None:
        for index, (label, variable) in enumerate(fields):
            column = index % columns
            row = start_row + (index // columns) * 2
            ttk.Label(parent, text=label).grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0, 8),
                pady=(0, 2),
            )
            ttk.Entry(parent, textvariable=variable, width=18).grid(
                row=row + 1,
                column=column,
                sticky="ew",
                padx=(0, 8),
                pady=(0, 6),
            )
            parent.columnconfigure(column, weight=1)

    def _build_dt_path_row(
        self,
        parent,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse_command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(
            row=row + 1,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 6),
        )
        ttk.Button(parent, text="Browse...", command=browse_command).grid(
            row=row + 1,
            column=1,
            sticky="ew",
            pady=(0, 6),
        )
        parent.columnconfigure(0, weight=1)

    def _choose_dt_model_path(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select Simulink model",
            filetypes=[("Simulink models", "*.slx"), ("All files", "*.*")],
        )
        if file_path:
            self.dt_model_path_var.set(self._display_path(file_path))
            self._refresh_dt_command_preview()

    def _choose_dt_runner_path(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select digital-twin runner",
            filetypes=[("Python scripts", "*.py"), ("All files", "*.*")],
        )
        if file_path:
            self.dt_runner_path_var.set(self._display_path(file_path))
            self._refresh_dt_command_preview()

    def _choose_dt_save_path(
        self,
        variable: tk.StringVar,
        title: str,
        default_extension: str,
        filetypes,
    ) -> None:
        file_path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=default_extension,
            filetypes=filetypes,
        )
        if file_path:
            variable.set(self._display_path(file_path))
            self._refresh_dt_command_preview()

    def _start_dt_session(self) -> None:
        if self.dt_process is not None and self.dt_process.poll() is None:
            self.dt_status_var.set("Autonomous DT session is already running.")
            return

        try:
            command = self._build_dt_command()
        except Exception as exc:
            messagebox.showerror("Invalid autonomous DT settings", str(exc))
            return

        self._set_text_widget(self.dt_output_text, "")
        self._reset_dt_live_state()
        self._set_text_widget(
            self.dt_command_preview_text,
            self._format_command(command),
        )
        self._append_dt_output("[gui] Starting autonomous DT runner...\n")
        self._append_dt_output(f"[gui] {self._format_command(command)}\n\n")

        repo_root = self._repo_root()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            self.dt_stop_requested = False
            self.dt_process = subprocess.Popen(
                command,
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except Exception as exc:
            self.dt_process = None
            self._append_dt_output(f"[gui] Failed to start runner: {exc}\n")
            self.dt_status_var.set("Autonomous DT session failed to start.")
            return

        self._set_dt_running(True)
        self.dt_status_var.set(
            f"Autonomous DT session running (pid {self.dt_process.pid})."
        )

        worker = threading.Thread(
            target=self._read_dt_process_worker,
            args=(self.dt_process,),
            daemon=True,
        )
        worker.start()

    def _read_dt_process_worker(self, process) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self.event_queue.put({"type": "dt_output", "line": line})
            return_code = process.wait()
            self.event_queue.put(
                {
                    "type": "dt_complete",
                    "returncode": return_code,
                    "pid": process.pid,
                }
            )
        except Exception as exc:
            self.event_queue.put(
                {
                    "type": "dt_error",
                    "error": str(exc),
                    "pid": getattr(process, "pid", None),
                }
            )

    def _stop_dt_session(self) -> None:
        process = self.dt_process
        if process is None or process.poll() is not None:
            self.dt_status_var.set("No autonomous DT session is running.")
            self._set_dt_running(False)
            return

        self.dt_stop_requested = True
        self.dt_status_var.set("Stopping autonomous DT session...")
        self.dt_stop_button.configure(state="disabled")
        self._append_dt_output("\n[gui] Stop requested; terminating runner...\n")

        worker = threading.Thread(
            target=self._terminate_dt_process_worker,
            args=(process,),
            daemon=True,
        )
        worker.start()

    def _terminate_dt_process_worker(self, process) -> None:
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.event_queue.put(
                    {
                        "type": "dt_output",
                        "line": "[gui] Runner did not exit after terminate; killing it.\n",
                    }
                )
                process.kill()
                process.wait(timeout=5)
        except Exception as exc:
            self.event_queue.put(
                {
                    "type": "dt_error",
                    "error": f"Failed to stop runner: {exc}",
                    "pid": getattr(process, "pid", None),
                }
            )

    def _handle_dt_complete(self, return_code: int, pid) -> None:
        if self.dt_process is not None and self.dt_process.pid == pid:
            self.dt_process = None

        self._set_dt_running(False)
        if self.dt_stop_requested:
            self.dt_status_var.set("Autonomous DT session stopped by user.")
            self._append_dt_output(f"\n[gui] Runner stopped with exit code {return_code}.\n")
        elif return_code == 0:
            self.dt_status_var.set("Autonomous DT session completed.")
            self._append_dt_output("\n[gui] Runner completed successfully.\n")
        else:
            self.dt_status_var.set(
                f"Autonomous DT session exited with code {return_code}."
            )
            self._append_dt_output(
                f"\n[gui] Runner exited with non-zero code {return_code}.\n"
            )
        self.dt_stop_requested = False

    def _handle_dt_error(self, error: str, pid) -> None:
        if self.dt_process is not None and self.dt_process.pid == pid:
            self.dt_process = None
        self._set_dt_running(False)
        self.dt_status_var.set(f"Autonomous DT runner error: {error}")
        self._append_dt_output(f"\n[gui] Runner error: {error}\n")
        self.dt_stop_requested = False

    def _set_dt_running(self, is_running: bool) -> None:
        if hasattr(self, "dt_start_button"):
            self.dt_start_button.configure(state="disabled" if is_running else "normal")
        if hasattr(self, "dt_stop_button"):
            self.dt_stop_button.configure(state="normal" if is_running else "disabled")
        if hasattr(self, "dt_copy_command_button"):
            self.dt_copy_command_button.configure(state="normal")
        if hasattr(self, "dt_open_report_button"):
            self.dt_open_report_button.configure(state="normal")

    def _append_dt_output(self, line: str) -> None:
        self.dt_output_text.configure(state="normal")
        self.dt_output_text.insert("end", line)
        self.dt_output_text.configure(state="disabled")
        self.dt_output_text.see("end")

    def _handle_dt_output_line(self, line: str) -> None:
        event = parse_dt_gui_event(line)
        if event is None:
            self._append_dt_output(line)
            return

        self._handle_dt_live_event(event)
        request = self._dt_event_summary(
            event,
            "request_summary",
            self._format_dt_intent(event.get("supervisor_request")),
        )
        runner_output = self._dt_event_summary(
            event,
            "runner_output_summary",
            self._format_dt_intent(event.get("guarded_udp_intent")),
        )
        local = self._dt_local_control_summary(event)
        feedback = self._dt_feedback_summary(event)
        sim_time = self._format_dt_measurement(event.get("sim_time_s"), "s")
        self._append_dt_output(
            f"[decision {event.get('tick_index', '?')} @ {sim_time}] "
            f"request={request} -> runner={runner_output} | "
            f"local={local} | feedback={feedback}\n"
        )

    def _handle_dt_live_event(self, event: Dict[str, Any]) -> None:
        self.dt_supervisor_request_var.set(
            self._dt_event_summary(
                event,
                "request_summary",
                self._format_dt_intent(event.get("supervisor_request")),
            )
        )
        self.dt_guarded_intent_var.set(
            self._dt_event_summary(
                event,
                "runner_output_summary",
                self._format_dt_intent(event.get("guarded_udp_intent")),
            )
        )
        self.dt_local_state_var.set(self._dt_local_control_summary(event))
        self.dt_measured_power_var.set(self._dt_feedback_summary(event))

        telemetry = event.get("telemetry_summary")
        if telemetry:
            self.dt_telemetry_var.set(str(telemetry))
        else:
            self.dt_telemetry_var.set(
                "  ".join(
                    (
                        "t="
                        + self._format_dt_measurement(event.get("sim_time_s"), "s"),
                        "Vbus="
                        + self._format_dt_measurement(event.get("v_bus_v"), "V"),
                        "SOC="
                        + self._format_dt_measurement(event.get("soc_pct"), "%"),
                    )
                )
            )

        note = str(
            event.get("interface_note")
            or event.get("python_adjustment")
            or "none"
        )
        self.dt_adjustment_var.set("Interface note: " + self._truncate(note, 120))

    def _reset_dt_live_state(self) -> None:
        self.dt_supervisor_request_var.set("Waiting for decision")
        self.dt_guarded_intent_var.set("Waiting for decision")
        self.dt_local_state_var.set("Waiting for telemetry")
        self.dt_measured_power_var.set("Waiting for telemetry")
        self.dt_telemetry_var.set("Waiting for DT telemetry")
        self.dt_adjustment_var.set("Interface note: no decision received")

    @staticmethod
    def _dt_event_summary(event: Dict[str, Any], key: str, fallback: str) -> str:
        summary = event.get(key)
        return str(summary) if summary not in (None, "") else fallback

    def _dt_local_control_summary(self, event: Dict[str, Any]) -> str:
        summary = event.get("local_control_summary")
        if summary not in (None, ""):
            return str(summary)
        local_state = event.get("reported_local_state") or {}
        state_name = str(local_state.get("name") or "NOT_REPORTED")
        state_code = local_state.get("code")
        return state_name if state_code is None else f"{state_name} [code {state_code}]"

    def _dt_feedback_summary(self, event: Dict[str, Any]) -> str:
        summary = event.get("feedback_summary")
        if summary not in (None, ""):
            return str(summary)
        return "P_batt = " + self._format_dt_measurement(
            event.get("p_batt_measured_w"),
            "W",
            signed=True,
        )

    @staticmethod
    def _format_dt_intent(command) -> str:
        if not isinstance(command, dict):
            return "No supervisor request"
        mode = str(command.get("mode") or "HOLD")
        power = AssistantGuiApp._format_dt_measurement(
            command.get("p_batt_cmd_w"),
            "W",
            signed=True,
        )
        if command.get("enable") is False:
            return f"{mode} {power} (disabled)"
        return f"{mode} {power}"

    @staticmethod
    def _format_dt_measurement(value, unit: str, signed: bool = False) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "--"
        number = f"{numeric:+.1f}" if signed else f"{numeric:.1f}"
        return f"{number} {unit}"

    def _copy_dt_command(self) -> None:
        try:
            command = self._build_dt_command()
        except Exception as exc:
            messagebox.showerror("Invalid autonomous DT settings", str(exc))
            return

        command_text = self._format_command(command)
        self._set_text_widget(self.dt_command_preview_text, command_text)
        self.root.clipboard_clear()
        self.root.clipboard_append(command_text)
        self.dt_status_var.set("Autonomous DT command copied to clipboard.")

    def _refresh_dt_command_preview(self) -> None:
        if not hasattr(self, "dt_command_preview_text"):
            return
        try:
            command_text = self._format_command(self._build_dt_command())
        except Exception as exc:
            command_text = f"Settings error: {exc}"
        self._set_text_widget(self.dt_command_preview_text, command_text)

    def _open_dt_report(self) -> None:
        path_text = self.dt_report_path_var.get().strip()
        if not path_text:
            self.dt_status_var.set("No report path is configured.")
            return

        report_path = self._resolve_dt_path(path_text)
        if not report_path.exists():
            self.dt_status_var.set(f"Report does not exist yet: {report_path}")
            return

        try:
            os.startfile(str(report_path))
        except Exception as exc:
            messagebox.showerror("Open report failed", str(exc))

    def _build_dt_command(self) -> list[str]:
        runner_value = self.dt_runner_path_var.get().strip()
        if not runner_value:
            raise ValueError("Choose a DT runner script.")
        runner_path = self._resolve_dt_path(runner_value)
        if not runner_path.exists():
            raise FileNotFoundError(f"Runner script not found: {runner_path}")

        command = [sys.executable, str(runner_path), "--emit-gui-events"]

        self._append_dt_option(command, "--backend", self.dt_backend_var)
        self._append_dt_option(command, "--policy", self.dt_policy_var)

        for option, variable in (
            ("--tick-seconds", self.dt_tick_seconds_var),
            ("--startup-grace-seconds", self.dt_startup_grace_seconds_var),
            ("--max-sim-seconds", self.dt_max_sim_seconds_var),
            ("--success-hold-seconds", self.dt_success_hold_seconds_var),
        ):
            self._append_dt_option(command, option, variable)

        if self.dt_real_time_var.get():
            command.append("--real-time")

        self._append_dt_option(command, "--model-name", self.dt_model_name_var)
        self._append_dt_option(command, "--model-path", self.dt_model_path_var)

        if self.dt_backend_var.get() == "udp":
            for option, variable in (
                ("--udp-command-host", self.dt_udp_command_host_var),
                ("--udp-command-port", self.dt_udp_command_port_var),
                ("--udp-observation-host", self.dt_udp_observation_host_var),
                ("--udp-observation-port", self.dt_udp_observation_port_var),
                ("--udp-timeout", self.dt_udp_timeout_var),
                ("--udp-reset-timeout", self.dt_udp_reset_timeout_var),
                (
                    "--udp-command-resend-period",
                    self.dt_udp_command_resend_period_var,
                ),
            ):
                self._append_dt_option(command, option, variable)
            if self.dt_udp_send_reset_var.get():
                command.append("--udp-send-reset")
            if self.dt_udp_republish_enabled_var.get():
                self._append_dt_option(
                    command,
                    "--udp-republish-host",
                    self.dt_udp_republish_host_var,
                )
                self._append_dt_option(
                    command,
                    "--udp-republish-port",
                    self.dt_udp_republish_port_var,
                )

        if self.dt_policy_var.get() == "llm":
            for option, variable in (
                ("--llm-base-url", self.dt_llm_base_url_var),
                ("--llm-model", self.dt_llm_model_var),
                ("--llm-api-key", self.dt_llm_api_key_var),
                ("--llm-temperature", self.dt_llm_temperature_var),
                ("--llm-max-tokens", self.dt_llm_max_tokens_var),
            ):
                self._append_dt_option(command, option, variable)
            if self.dt_llm_verbose_var.get():
                command.append("--llm-verbose")
            if self.dt_llm_strict_var.get():
                command.append("--llm-strict")
            if self.dt_append_llm_log_var.get():
                command.append("--append-llm-log")
            self._append_dt_option(command, "--llm-log", self.dt_llm_log_path_var)

        self._append_dt_option(command, "--csv", self.dt_csv_path_var)
        self._append_dt_option(command, "--report", self.dt_report_path_var)
        command.extend(self._dt_model_input_arguments())

        return command

    def _dt_model_input_arguments(self) -> list[str]:
        if not hasattr(self, "dt_model_inputs_text"):
            return []

        arguments: list[str] = []
        value = self.dt_model_inputs_text.get("1.0", "end").strip()
        for line_number, line in enumerate(value.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                parts = shlex.split(stripped, posix=False)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid DT-specific argument on line {line_number}: {exc}"
                ) from exc
            for part in parts:
                if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
                    part = part[1:-1]
                arguments.append(part)
        return arguments

    def _append_dt_option(self, command: list[str], option: str, variable) -> None:
        value = str(variable.get()).strip()
        if value:
            command.extend([option, value])

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _resolve_dt_path(self, path_text: str) -> Path:
        path = Path(path_text)
        if path.is_absolute():
            return path
        return self._repo_root() / path

    def _display_path(self, path_text: str) -> str:
        path = Path(path_text)
        try:
            return str(path.relative_to(self._repo_root()))
        except ValueError:
            return str(path)

    @staticmethod
    def _format_command(command: list[str]) -> str:
        return subprocess.list2cmdline(command)

    def _configure_tags(self) -> None:
        self.chat_text.tag_configure(
            "user",
            foreground="#144b7d",
            font=("Segoe UI Semibold", 10),
        )
        self.chat_text.tag_configure(
            "assistant",
            foreground="#0a6b47",
            font=("Segoe UI Semibold", 10),
        )
        self.chat_text.tag_configure(
            "system",
            foreground="#7c2d12",
            font=("Segoe UI Semibold", 10),
        )
        self.chat_text.tag_configure("body", foreground="#202124")

    def _send_query_event(self, _event) -> str:
        self._send_query()
        return "break"

    def _run_database_query_event(self, _event) -> str:
        self._run_database_query()
        return "break"

    def _send_query(self) -> None:
        if self.is_busy:
            return

        user_query = self.input_text.get("1.0", "end").strip()
        if not user_query:
            return

        self.input_text.delete("1.0", "end")
        self._reset_turn_views()
        self._append_chat_message("User", user_query, "user")
        self._set_busy(True, "Running turn...")

        worker = threading.Thread(
            target=self._run_turn_worker,
            args=(user_query,),
            daemon=True,
        )
        worker.start()

    def _run_turn_worker(self, user_query: str) -> None:
        try:
            self.conversation.tool_loop_runner.set_event_callback(
                self._queue_tool_event
            )
            result = self.conversation.run_turn(user_query)
            self.event_queue.put({"type": "turn_complete", "result": result})
        except Exception as exc:
            self.event_queue.put({"type": "turn_exception", "error": str(exc)})

    def _run_database_query(self) -> None:
        if self.database_query_busy:
            return

        collection_name = self.selected_collection_var.get().strip()
        query_text = self.database_query_var.get().strip()
        top_k = max(1, int(self.database_limit_var.get()))

        if not collection_name:
            self.database_status_var.set("Select a collection before querying.")
            return
        if not query_text:
            self.database_status_var.set("Enter a query before running the search.")
            return

        self._set_database_query_busy(True)
        self.database_status_var.set(f"Querying {collection_name}...")

        worker = threading.Thread(
            target=self._run_database_query_worker,
            args=(collection_name, query_text, top_k),
            daemon=True,
        )
        worker.start()

    def _run_database_query_worker(
        self,
        collection_name: str,
        query_text: str,
        top_k: int,
    ) -> None:
        try:
            browser = getattr(self.conversation, "database_browser", None)
            if browser is None:
                raise RuntimeError("No database browser is attached to the conversation.")

            result = browser.query_collection(
                collection_name=collection_name,
                query=query_text,
                top_k=top_k,
            )
            self.event_queue.put(
                {
                    "type": "database_query_complete",
                    "result": result,
                }
            )
        except Exception as exc:
            self.event_queue.put(
                {
                    "type": "database_query_error",
                    "error": str(exc),
                }
            )

    def _clear_selected_collection(self) -> None:
        if self.database_query_busy:
            return

        collection_name = self.selected_collection_var.get().strip()
        if not collection_name:
            self.database_status_var.set("Select a collection before clearing it.")
            return

        confirmed = messagebox.askyesno(
            "Clear collection",
            f"Clear all documents from collection '{collection_name}'?",
            icon="warning",
        )
        if not confirmed:
            return

        self._set_database_query_busy(True)
        self.database_status_var.set(f"Clearing {collection_name}...")
        worker = threading.Thread(
            target=self._run_collection_action_worker,
            args=("clear", collection_name),
            daemon=True,
        )
        worker.start()

    def _delete_selected_collection(self) -> None:
        if self.database_query_busy:
            return

        collection_name = self.selected_collection_var.get().strip()
        if not collection_name:
            self.database_status_var.set("Select a collection before deleting it.")
            return

        confirmed = messagebox.askyesno(
            "Delete collection",
            f"Delete collection '{collection_name}' entirely?",
            icon="warning",
        )
        if not confirmed:
            return

        self._set_database_query_busy(True)
        self.database_status_var.set(f"Deleting {collection_name}...")
        worker = threading.Thread(
            target=self._run_collection_action_worker,
            args=("delete", collection_name),
            daemon=True,
        )
        worker.start()

    def _run_collection_action_worker(
        self,
        action: str,
        collection_name: str,
    ) -> None:
        try:
            browser = getattr(self.conversation, "database_browser", None)
            if browser is None:
                raise RuntimeError("No database browser is attached to the conversation.")

            if action == "clear":
                result = browser.clear_collection(collection_name)
            elif action == "delete":
                result = browser.delete_collection(collection_name)
            else:
                raise ValueError(f"Unknown collection action: {action}")

            self.event_queue.put(
                {
                    "type": "collection_action_complete",
                    "action": action,
                    "result": result,
                }
            )
        except Exception as exc:
            self.event_queue.put(
                {
                    "type": "collection_action_error",
                    "action": action,
                    "error": str(exc),
                }
            )

    def _ingest_text_entry(self) -> None:
        if self.ingest_busy:
            return

        collection_name = self.ingest_collection_var.get().strip()
        text = self.ingest_text.get("1.0", "end").strip()
        source = self.ingest_source_var.get().strip()

        if not collection_name:
            self.ingest_status_var.set("Choose or type a target collection name.")
            return
        if not text:
            self.ingest_status_var.set("Typed entry is empty.")
            return

        self._set_ingest_busy(True)
        self.ingest_status_var.set(f"Adding typed entry to {collection_name}...")

        worker = threading.Thread(
            target=self._run_text_ingest_worker,
            args=(collection_name, text, source),
            daemon=True,
        )
        worker.start()

    def _run_text_ingest_worker(
        self,
        collection_name: str,
        text: str,
        source: str,
    ) -> None:
        try:
            browser = getattr(self.conversation, "database_browser", None)
            if browser is None:
                raise RuntimeError("No database browser is attached to the conversation.")

            result = browser.add_text_entry(
                collection_name=collection_name,
                text=text,
                source=source or None,
            )
            self.event_queue.put({"type": "ingest_complete", "result": result, "mode": "text"})
        except Exception as exc:
            self.event_queue.put({"type": "ingest_error", "error": str(exc)})

    def _choose_ingest_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select a file to ingest",
            filetypes=[
                ("Supported documents", "*.txt *.md *.json *.csv *.py *.pdf *.docx"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            self.ingest_file_path_var.set(file_path)
            if not self.ingest_source_var.get().strip():
                self.ingest_source_var.set(file_path.split("\\")[-1])

    def _choose_ingest_folder(self) -> None:
        directory_path = filedialog.askdirectory(
            title="Select a folder to ingest",
        )
        if directory_path:
            self.ingest_folder_path_var.set(directory_path)

    def _ingest_selected_file(self) -> None:
        if self.ingest_busy:
            return

        collection_name = self.ingest_collection_var.get().strip()
        file_path = self.ingest_file_path_var.get().strip()
        source = self.ingest_source_var.get().strip()

        if not collection_name:
            self.ingest_status_var.set("Choose or type a target collection name.")
            return
        if not file_path:
            self.ingest_status_var.set("Choose a file before ingesting.")
            return

        self._set_ingest_busy(True)
        self.ingest_status_var.set(f"Adding file to {collection_name}...")

        worker = threading.Thread(
            target=self._run_file_ingest_worker,
            args=(collection_name, file_path, source),
            daemon=True,
        )
        worker.start()

    def _ingest_selected_folder(self) -> None:
        if self.ingest_busy:
            return

        collection_name = self.ingest_collection_var.get().strip()
        folder_path = self.ingest_folder_path_var.get().strip()
        recursive = bool(self.ingest_recursive_var.get())

        if not collection_name:
            self.ingest_status_var.set("Choose or type a target collection name.")
            return
        if not folder_path:
            self.ingest_status_var.set("Choose a folder before ingesting.")
            return

        self._set_ingest_busy(True)
        self.ingest_status_var.set(f"Adding folder to {collection_name}...")

        worker = threading.Thread(
            target=self._run_directory_ingest_worker,
            args=(collection_name, folder_path, recursive),
            daemon=True,
        )
        worker.start()

    def _run_file_ingest_worker(
        self,
        collection_name: str,
        file_path: str,
        source: str,
    ) -> None:
        try:
            browser = getattr(self.conversation, "database_browser", None)
            if browser is None:
                raise RuntimeError("No database browser is attached to the conversation.")

            result = browser.ingest_file(
                collection_name=collection_name,
                file_path=file_path,
                source=source or None,
            )
            self.event_queue.put({"type": "ingest_complete", "result": result, "mode": "file"})
        except Exception as exc:
            self.event_queue.put({"type": "ingest_error", "error": str(exc)})

    def _run_directory_ingest_worker(
        self,
        collection_name: str,
        folder_path: str,
        recursive: bool,
    ) -> None:
        try:
            browser = getattr(self.conversation, "database_browser", None)
            if browser is None:
                raise RuntimeError("No database browser is attached to the conversation.")

            result = browser.ingest_directory(
                collection_name=collection_name,
                directory_path=folder_path,
                recursive=recursive,
            )
            self.event_queue.put(
                {"type": "ingest_complete", "result": result, "mode": "directory"}
            )
        except Exception as exc:
            self.event_queue.put({"type": "ingest_error", "error": str(exc)})

    def _queue_tool_event(self, event: Dict[str, Any]) -> None:
        self.event_queue.put({"type": "tool_event", "event": event})

    def _schedule_queue_poll(self) -> None:
        self.root.after(self.POLL_INTERVAL_MS, self._process_event_queue)

    def _process_event_queue(self) -> None:
        while True:
            try:
                payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            event_type = payload["type"]
            if event_type == "tool_event":
                self._add_tool_event(payload["event"])
            elif event_type == "turn_complete":
                self._handle_turn_complete(payload["result"])
            elif event_type == "turn_exception":
                self._append_chat_message(
                    "System",
                    f"Unexpected GUI/backend error: {payload['error']}",
                    "system",
                )
                self._set_busy(False, "Turn failed unexpectedly.")
            elif event_type == "database_query_complete":
                self._handle_database_query_complete(payload["result"])
            elif event_type == "database_query_error":
                self.database_status_var.set(f"Database query failed: {payload['error']}")
                self._set_database_query_busy(False)
            elif event_type == "collection_action_complete":
                self._handle_collection_action_complete(
                    payload["action"],
                    payload["result"],
                )
            elif event_type == "collection_action_error":
                self.database_status_var.set(
                    f"Collection {payload['action']} failed: {payload['error']}"
                )
                self._set_database_query_busy(False)
            elif event_type == "ingest_complete":
                self._handle_ingest_complete(payload["result"], payload["mode"])
            elif event_type == "ingest_error":
                self.ingest_status_var.set(f"Ingest failed: {payload['error']}")
                self._set_ingest_busy(False)
            elif event_type == "dt_output":
                self._handle_dt_output_line(payload["line"])
            elif event_type == "dt_complete":
                self._handle_dt_complete(payload["returncode"], payload["pid"])
            elif event_type == "dt_error":
                self._handle_dt_error(payload["error"], payload.get("pid"))

        self._schedule_queue_poll()

    def _handle_turn_complete(self, result: Dict[str, Any]) -> None:
        self._append_chat_message("Assistant", result["final_response"], "assistant")
        self._populate_summary(result)
        self._populate_rag_matches(result["rag_matches"])
        self._set_text_widget(
            self.initial_messages_text,
            json.dumps(result["initial_messages"], indent=2),
        )
        self._set_text_widget(
            self.working_messages_text,
            json.dumps(result["working_messages"], indent=2),
        )

        if result["error"] and result["finished"] is False:
            self.status_var.set(f"Turn completed with error: {result['error']}")
        else:
            self.status_var.set("Turn completed.")

        self._set_busy(False, self.status_var.get())

    def _handle_database_query_complete(self, result: Dict[str, Any]) -> None:
        self._populate_database_query_results(result)
        self.database_status_var.set(
            f"Found {len(result['matches'])} matches in {result['collection_name']}."
        )
        self._set_database_query_busy(False)

    def _handle_collection_action_complete(
        self,
        action: str,
        result: Dict[str, Any],
    ) -> None:
        self._populate_database_collections()
        self.database_status_var.set(
            f"Collection {result['collection_name']} {result['status']} "
            f"({result.get('deleted_count', 0)} removed)."
        )
        self._set_text_widget(
            self.database_result_detail_text,
            json.dumps(result, indent=2),
        )
        self._set_database_query_busy(False)

    def _handle_ingest_complete(self, result: Dict[str, Any], mode: str) -> None:
        self._populate_database_collections()
        self.selected_collection_var.set(result["collection_name"])
        self.ingest_collection_var.set(result["collection_name"])
        self._set_text_widget(
            self.ingest_result_text,
            json.dumps(result, indent=2),
        )
        if mode == "text":
            self.ingest_text.delete("1.0", "end")
        if mode == "file":
            self.ingest_file_path_var.set("")
        if mode == "directory":
            self.ingest_folder_path_var.set("")
        self.ingest_status_var.set(
            f"Added {mode} content to {result['collection_name']}."
        )
        self._set_ingest_busy(False)

    def _populate_summary(self, result: Dict[str, Any]) -> None:
        self.summary_finished_var.set(str(result["finished"]))
        self.summary_rounds_var.set(str(result["rounds_used"]))
        self.summary_rag_var.set(str(len(result["rag_matches"])))
        self.summary_tools_var.set(str(len(result["tool_trace"])))

        summary_payload = {
            "final_response": result["final_response"],
            "finished": result["finished"],
            "error": result["error"],
            "rounds_used": result["rounds_used"],
            "rag_match_count": len(result["rag_matches"]),
            "tool_call_count": len(result["tool_trace"]),
            "tool_trace": [asdict(item) for item in result["tool_trace"]],
        }
        self._set_text_widget(
            self.summary_text,
            json.dumps(summary_payload, indent=2),
        )

    def _populate_rag_matches(self, rag_matches) -> None:
        self.rag_items.clear()
        for item in self.rag_tree.get_children():
            self.rag_tree.delete(item)

        for index, chunk in enumerate(rag_matches, start=1):
            item_id = f"rag_{index}"
            score = "" if chunk.score is None else f"{chunk.score:.4f}"
            preview = present_retrieval_content(
                chunk.content,
                getattr(chunk, "metadata", None),
            ).preview
            self.rag_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(chunk.source, score, preview),
            )
            self.rag_items[item_id] = chunk

        self._set_text_widget(self.rag_detail_text, "")

    def _populate_database_collections(self) -> None:
        browser = getattr(self.conversation, "database_browser", None)
        collections = browser.list_collections() if browser is not None else []
        selected_collection = self.selected_collection_var.get()
        ingest_collection = self.ingest_collection_var.get()

        self.database_items.clear()
        for item in self.database_tree.get_children():
            self.database_tree.delete(item)

        collection_names = []
        for index, collection in enumerate(collections, start=1):
            item_id = f"collection_{index}"
            count = "" if collection["count"] is None else str(collection["count"])
            self.database_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(collection["name"], count),
            )
            self.database_items[item_id] = collection
            collection_names.append(collection["name"])

        self.database_collection_combo["values"] = collection_names
        self.ingest_collection_combo["values"] = collection_names

        if selected_collection in collection_names:
            self.selected_collection_var.set(selected_collection)
        elif collection_names:
            self.selected_collection_var.set(collection_names[0])
        else:
            self.selected_collection_var.set("")

        if ingest_collection:
            self.ingest_collection_var.set(ingest_collection)
        elif collection_names:
            self.ingest_collection_var.set(collection_names[0])
        else:
            self.ingest_collection_var.set("")

    def _populate_database_query_results(self, result: Dict[str, Any]) -> None:
        self.database_query_items.clear()
        for item in self.database_results_tree.get_children():
            self.database_results_tree.delete(item)

        for index, match in enumerate(result["matches"], start=1):
            item_id = f"db_match_{index}"
            score = "" if match["score"] is None else f"{match['score']:.4f}"
            preview = present_retrieval_content(
                match.get("content", ""),
                match.get("metadata", {}),
            ).preview
            self.database_results_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(index, match["id"], score, preview),
            )
            enriched_match = dict(match)
            enriched_match["collection_name"] = result["collection_name"]
            enriched_match["query"] = result["query"]
            self.database_query_items[item_id] = enriched_match

        self._set_text_widget(self.database_result_detail_text, "")

    def _populate_available_tools(self) -> None:
        tools = getattr(
            self.conversation,
            "available_tools",
            getattr(self.conversation.tool_loop_runner, "tools", []),
        )

        self.available_tool_items.clear()
        for item in self.available_tools_tree.get_children():
            self.available_tools_tree.delete(item)

        for index, tool in enumerate(tools, start=1):
            function_def = tool.get("function", {})
            parameters = function_def.get("parameters", {})
            required = ", ".join(parameters.get("required", [])) or "-"
            item_id = f"available_tool_{index}"
            self.available_tools_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    function_def.get("name", ""),
                    required,
                    self._truncate(function_def.get("description", ""), 110),
                ),
            )
            self.available_tool_items[item_id] = tool

        self._set_text_widget(self.available_tool_detail_text, "")

    def _add_tool_event(self, event: Dict[str, Any]) -> None:
        self.tool_event_counter += 1
        item_id = f"tool_event_{self.tool_event_counter}"
        round_number = event.get("round_number", "")
        tool_name = event.get("tool_name", "")
        status = "ok"

        if event["type"] == "model_error" or event.get("error"):
            status = "error"
        elif event["type"] == "tool_started":
            status = "running"
        elif event["type"] == "round_started":
            status = "start"

        self.tool_tree.insert(
            "",
            "end",
            iid=item_id,
            values=(round_number, event["type"], tool_name, status),
        )
        self.tool_tree.see(item_id)
        self.tool_event_items[item_id] = event

    def _on_rag_select(self, _event) -> None:
        selection = self.rag_tree.selection()
        if not selection:
            return

        chunk = self.rag_items[selection[0]]
        self._set_text_widget(
            self.rag_detail_text,
            render_detail_text(build_context_chunk_detail_payload(chunk)),
        )

    def _on_database_select(self, _event) -> None:
        selection = self.database_tree.selection()
        if not selection:
            return

        collection = self.database_items[selection[0]]
        self.selected_collection_var.set(collection["name"])
        self.ingest_collection_var.set(collection["name"])
        self.database_status_var.set(
            f"Selected {collection['name']} with count {collection['count']}."
        )

    def _on_database_result_select(self, _event) -> None:
        selection = self.database_results_tree.selection()
        if not selection:
            return

        match = self.database_query_items[selection[0]]
        self._set_text_widget(
            self.database_result_detail_text,
            render_detail_text(build_search_match_detail_payload(match)),
        )

    def _on_tool_select(self, _event) -> None:
        selection = self.tool_tree.selection()
        if not selection:
            return

        event = self.tool_event_items[selection[0]]
        self._set_text_widget(
            self.tool_detail_text,
            json.dumps(self._json_safe(event), indent=2),
        )

    def _on_available_tool_select(self, _event) -> None:
        selection = self.available_tools_tree.selection()
        if not selection:
            return

        tool = self.available_tool_items[selection[0]]
        self._set_text_widget(
            self.available_tool_detail_text,
            json.dumps(self._json_safe(tool), indent=2),
        )

    def _on_close(self) -> None:
        process = self.dt_process
        if process is not None and process.poll() is None:
            confirmed = messagebox.askyesno(
                "Autonomous DT session running",
                "Stop the running autonomous DT session and close the GUI?",
                icon="warning",
            )
            if not confirmed:
                return
            try:
                process.terminate()
            except Exception:
                pass
        self.root.destroy()

    def _clear_chat(self) -> None:
        if self.is_busy:
            return
        self.conversation.chat_memory.clear()
        self._set_text_widget(self.chat_text, "", preserve_state=False)
        self._reset_turn_views()
        self.status_var.set("Chat memory cleared.")

    def _reset_turn_views(self) -> None:
        self.tool_event_counter = 0
        self.rag_items.clear()
        self.tool_event_items.clear()

        for tree in (self.rag_tree, self.tool_tree):
            for item in tree.get_children():
                tree.delete(item)

        for widget in (
            self.rag_detail_text,
            self.tool_detail_text,
            self.initial_messages_text,
            self.working_messages_text,
            self.summary_text,
        ):
            self._set_text_widget(widget, "")

        self.summary_finished_var.set("n/a")
        self.summary_rounds_var.set("0")
        self.summary_rag_var.set("0")
        self.summary_tools_var.set("0")

    def _append_chat_message(self, speaker: str, body: str, speaker_tag: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", f"{speaker}\n", speaker_tag)
        self.chat_text.insert("end", f"{body}\n\n", "body")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _set_text_widget(
        self,
        widget,
        content: str,
        preserve_state: bool = True,
    ) -> None:
        current_state = widget.cget("state") if preserve_state else "normal"
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state=current_state if preserve_state else "disabled")

    def _set_busy(self, is_busy: bool, status_text: str) -> None:
        self.is_busy = is_busy
        state = "disabled" if is_busy else "normal"
        self.send_button.configure(state=state)
        self.input_text.configure(state=state)
        self.status_var.set(status_text)
        if not is_busy:
            self.input_text.focus_set()

    def _set_database_query_busy(self, is_busy: bool) -> None:
        self.database_query_busy = is_busy
        combo_state = "disabled" if is_busy else "readonly"
        self.database_collection_combo.configure(state=combo_state)
        self.database_refresh_button.configure(
            state="disabled" if is_busy else "normal"
        )
        self.database_clear_button.configure(
            state="disabled" if is_busy else "normal"
        )
        self.database_delete_button.configure(
            state="disabled" if is_busy else "normal"
        )
        self.database_query_entry.configure(
            state="disabled" if is_busy else "normal"
        )
        self.database_limit_spinbox.configure(
            state="disabled" if is_busy else "normal"
        )
        self.database_query_button.configure(
            state="disabled" if is_busy else "normal"
        )

    def _set_ingest_busy(self, is_busy: bool) -> None:
        self.ingest_busy = is_busy
        control_state = "disabled" if is_busy else "normal"
        self.ingest_collection_combo.configure(state=control_state)
        self.ingest_source_entry.configure(state=control_state)
        self.ingest_text.configure(state=control_state)
        self.ingest_file_entry.configure(state=control_state)
        self.ingest_folder_entry.configure(state=control_state)
        button_state = "disabled" if is_busy else "normal"
        self.ingest_text_button.configure(state=button_state)
        self.ingest_browse_button.configure(state=button_state)
        self.ingest_file_button.configure(state=button_state)
        self.ingest_folder_browse_button.configure(state=button_state)
        self.ingest_folder_recursive_check.configure(state=control_state)
        self.ingest_folder_button.configure(state=button_state)

    @staticmethod
    def _truncate(value: str, length: int) -> str:
        if len(value) <= length:
            return value
        return value[: length - 3] + "..."

    def _json_safe(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value
