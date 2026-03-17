(function () {
  'use strict';

  const STORAGE_KEY = 'ace_ui_lang'; 

  const I18N = {
    en: {
      "sub.sampling.title": "Sampling",
      "sub.sampling.desc": "Core diffusion controls: steps, guidance and CFG interval.",
      "sub.quality.title": "Quality scoring",
      "sub.quality.desc": "Controls how quality metrics influence selection (if enabled).",
      "sub.audio.title": "Audio post-processing",
      "sub.audio.desc": "Normalization and loudness-related controls.",
      "sub.latent.title": "Latent / VAE",
      "sub.latent.desc": "Latent shift and rescale before VAE decoding.",
      "sub.output.title": "Output",
      "sub.output.desc": "Batch and audio format.",
      
      'title.page': 'AceFlow',
      'ui.lang.label': 'UI language:',
      'ui.lang.auto': 'Auto',
      'ui.lang.en': 'English',
      'ui.lang.it': 'Italiano',
      'auth.login.title': 'Sign in',
      'auth.login.help': 'Sign in to enter the protected ACE-Step workspace and use AceFlow tools.',
      'auth.kicker': 'Protected access',
      'auth.hero.copy': 'You are entering the protected ACE-Step workspace for generation, remix, and LoRA management.',
      'auth.hero.pill_music': 'Music generation',
      'auth.hero.pill_remix': 'Remix workflow',
      'auth.hero.pill_lora': 'LoRA ready',
      'auth.hero.note': 'Use your account to continue. If you are signing in with a temporary password, the app will ask you to replace it immediately.',
      'auth.login.email': 'Email',
      'auth.login.password': 'Password',
      'auth.login.submit': 'Sign in',
      'auth.logout': 'Log out',
      'auth.admin.open': 'Users',
      'auth.change.title': 'Change your password',
      'auth.change.help': 'You are using a temporary password. Replace it now to unlock the workspace.',
      'auth.change.new_password': 'New password',
      'auth.change.confirm_password': 'Confirm new password',
      'auth.change.submit': 'Save password',
      'auth.status.login_failed': 'Login failed: {msg}',
      'auth.status.password_changed': 'Password updated. You can continue.',
      'auth.status.password_change_failed': 'Password change failed: {msg}',
      'auth.status.password_mismatch': 'The two passwords do not match.',
      'auth.status.password_short': 'Use at least 10 characters.',
      'auth.status.session_required': 'Sign in to continue.',
      'auth.status.password_required': 'Change your temporary password to continue.',
      'auth.admin.title': 'User access',
      'auth.admin.help': 'Create users with a temporary password. Each account has a single active session bound to the login IP.',
      'auth.admin.email': 'User email',
      'auth.admin.role': 'Role',
      'auth.role.user': 'User',
      'auth.role.admin': 'Admin',
      'auth.admin.create': 'Create user',
      'auth.admin.temp_password': 'Temporary password (show once)',
      'auth.admin.user_list': 'Existing users',
      'auth.admin.audit_title': 'Recent access events',
      'auth.admin.audit_empty': 'No access events yet.',
      'auth.admin.created': 'User created: {email}',
      'auth.admin.create_failed': 'User creation failed: {msg}',
      'auth.admin.list_failed': 'Could not load users: {msg}',
      'auth.admin.audit_failed': 'Could not load access events: {msg}',
      'auth.admin.no_users': 'No users found.',
      'auth.admin.must_change': 'Must change password',
      'auth.admin.last_login': 'Last login',
      'auth.admin.delete': 'Delete',
      'auth.admin.deleting': 'Deleting…',
      'auth.admin.deleted': 'User deleted: {email}',
      'auth.admin.delete_failed': 'User deletion failed: {msg}',
      'auth.admin.delete_confirm': 'Delete user {email}? This cannot be undone.',
      'auth.admin.delete_self_disabled': 'Current session',
      'auth.admin.reload_warning': 'list refresh failed; UI kept the local deletion result',
      'auth.error.missing_email_or_password': 'Enter both email and password.',
      'auth.error.invalid_credentials': 'Invalid credentials.',
      'auth.error.password_too_short': 'Use at least 10 characters.',
      'auth.error.user_not_found': 'User not found.',
      'auth.error.invalid_email': 'Enter a valid email address.',
      'auth.error.user_already_exists': 'User already exists.',
      'auth.error.delete_self': 'You cannot delete your own account.',
      'auth.error.delete_last_admin': 'You cannot delete the last admin account.',
      'auth.error.admin_only': 'Admin only.',
      'auth.error.auth_disabled': 'Authentication is disabled.',
      'auth.event.ok': 'ok',
      'auth.event.fail': 'failed',
      'auth.event.bootstrap_admin': 'Bootstrap admin',
      'auth.event.login': 'Login',
      'auth.event.logout': 'Logout',
      'auth.event.change_password': 'Password change',
      'auth.event.create_user': 'User creation',
      'auth.event.delete_user': 'User deletion',
      'auth.event.session_ip_mismatch': 'Session invalidated (IP mismatch)',

      'title.generate_song': 'Generate song',
      'help.queue_info': 'Your request will be queued and processed by the server.',
      'help.queue_ttl': 'Generated songs remain available on the server for the configured retention window, then they are automatically deleted unless cleanup is disabled.',
      'label.generation_mode': '🎛️ Mode',
      'mode.simple': 'Simple',
      'mode.custom': 'Custom',
      'mode.cover': 'Cover',
      'mode.remix': 'Remix',
      'btn.random_from_archive': 'Random from archive',

      'label.ref_song': 'Reference song',
      'help.ref_song_upload': 'Upload an audio file when using Cover/Remix.',

      'label.style': '🎨 Style / prompt',
      'ph.style': 'Describe style, mood, instruments…',
      'label.lyrics': '✍️ Lyrics',
      'ph.lyrics': 'Paste lyrics here (or leave empty for instrumental).',

      'label.duration_seconds': 'Duration (seconds)',
      'label.bpm': 'BPM',
      'ph.auto': '(auto)',
      'label.seed': 'Seed',
      'opt.auto': 'Auto',
      'opt.seed_random': 'Random seed',

      'label.key_scale': 'Key / scale',
      'ph.key_scale': 'e.g. C major',
      'label.key_root': 'Key',
      'label.key_mode': 'Mode',
      'opt.key_mode_major': 'Major',
      'opt.key_mode_minor': 'Minor',
      'label.time_signature': 'Time signature',
      'label.vocal_language': 'Vocal language',

      'opt.instrumental': 'Instrumental (no vocals)',
      'opt.think_lm': 'Use LM (lyrics assistant)',
      'help.think_lm': 'When enabled, the server uses a language model to help draft/structure lyrics for better alignment.',

      
      'title.lora_style': 'LoRA style',
      'help.lora': 'Optional: apply a LoRA style preset.',
      'label.select_lora': 'Select LoRA',
      'label.lora_weight': 'LoRA weight',
      'help.lora_weight': 'Higher = stronger style influence.',
      'lora.loading': 'Loading…',
      'lora.none': '(No LoRA)',
      'lora.none_short': 'none',
      'opt.ab_compare': 'Generate Audio 1 / Audio 2 compare (without LoRA vs with LoRA)',
      'help.ab_compare': 'Generates two songs with the same seed and parameters. Batch size is ignored and treated as 1 while compare mode is active.',
      'ab.compare_title': 'Audio 1 / Audio 2 Controls',
      'ab.compare_desc': 'The normal players stay untouched. These controls act on both together.',
      'ab.audio1': 'Audio 1',
      'ab.audio2': 'Audio 2',
      'ab.play_pause': 'Play/Pause both',
      'ab.stop': 'Stop both',
      'ab.crossfade': 'Crossfade',
      'ab.batch_locked': 'Batch size is locked to 1 while compare mode is active.',

      
      'title.chord_progression': '🎼 Chord progression',
      'help.chord_progression': 'Define a Roman-numeral progression and apply a clean harmonic layer to style, lyrics, key and BPM without touching the backend contract.',
      'label.chord_key': 'Key',
      'help.chord_key': 'Root note used to resolve the Roman progression into real chords.',
      'label.chord_scale': 'Scale',
      'help.chord_scale': 'Choose the tonal mode used to resolve the progression.',
      'label.chord_roman': 'Roman progression',
      'help.chord_roman': 'Examples: I - V - vi - IV, ii7 - V7 - Imaj7, i - bVII - bVI - V.',
      'ph.chord_roman': 'I - V - vi - IV',
      'label.chord_section_map': 'Section overrides',
      'help.chord_section_map': 'Optional. One rule per line, for example Verse=I - vi - IV - V or Chorus: vi - IV - I - V. Matching lyrics sections use their own progression.',
      'ph.chord_section_map': 'Verse=I - vi - IV - V\nChorus=vi - IV - I - V',
      'opt.scale_major': 'Major',
      'opt.scale_minor': 'Minor',
      'opt.chord_apply_keyscale': 'Apply resolved key/scale',
      'help.chord_apply_keyscale': 'Writes the resolved key and scale into the existing Key/Scale control.',
      'opt.chord_apply_bpm': 'Keep current BPM as manual',
      'help.chord_apply_bpm': 'When applying chords, keeps the current BPM value and turns BPM Auto off.',
      'opt.chord_apply_lyrics': 'Inject chord tags into lyrics',
      'help.chord_apply_lyrics': 'Applies chord tags to the real section headers already present in the lyrics. If no supported sections are found, only the global progression header is added.',
      'label.chord_preview_resolved': 'Resolved progression',
      'label.chord_preview_caption': 'Caption tag',
      'label.chord_preview_keyscale': 'Key/Scale tag',
      'label.chord_preview_sections': 'Section map',
      'btn.chord_generate': 'Generate sensible progression',
      'help.chord_generate': 'Creates a musically sensible Roman progression based on the selected key and scale.',
      'btn.chord_auto_sections': 'Auto section overrides',
      'help.chord_auto_sections': 'Reads supported section headers in the lyrics and builds section-aware overrides with musically plausible variation from the current progression.',
      'btn.chord_apply': 'Apply harmony',
      'help.chord_apply': 'Applies the resolved harmony to caption, key/scale and lyrics without changing generation mode.',
      'btn.chord_apply_full': 'Apply full harmony',
      'help.chord_apply_full_notice': 'Uses the generated harmonic reference as audio codes in Custom mode, or as pure WAV reference audio in Cover mode.',
      'btn.chord_remove': 'Clear chord setup',
      'help.chord_remove': 'Clears chord tags from caption and lyrics, resets the roman progression and section overrides, and removes chord-conditioning state from the UI.',
      'status.chord_applied': 'Harmony applied: {desc}',
      'status.chord_sections_applied': 'Section overrides active: {count}.',
      'status.chord_sections_none': 'Global progression only.',
      'status.chord_full_ready': 'Full harmony ready: harmonic reference and audio codes prepared for about {duration}s and linked to backend conditioning.',
      'status.chord_generated': 'Generated progression: {roman}',
      'status.chord_sections_generated': 'Section overrides generated from the current lyrics structure.',
      'status.chord_removed': 'Chord setup cleared from style, lyrics, progression, and section overrides.',
      'status.chord_full_cleared': 'Chord conditioning cleared from cover audio and audio codes.',
      'status.chord_full_uploading': 'Reference audio generation in progress…',
      'status.chord_full_extracting': 'Extracting audio codes from reference…',
      'error.chord_empty': 'Enter a Roman progression first.',
      'error.chord_token_invalid': 'Invalid Roman token: {token}',
      'error.chord_key_invalid': 'Invalid chord key.',
      'error.chord_full_failed': 'Full harmony failed: {msg}',
      'error.chord_section_line_invalid': 'Invalid section rule: {line}',
      'error.chord_sections_missing': 'No supported lyrics sections found for auto section overrides.',
      'title.advanced_settings': '🛠️ Advanced settings',
      'title.lm_settings': '🧠 LM settings',
      'help.lm_settings': 'These settings control the 5Hz Language Model used to plan and generate the lyrics/text.',
      'label.lm_temperature': 'LM temperature',
      'label.lm_cfg_scale': 'LM CFG scale',
      'label.lm_top_k': 'LM top‑K',
      'help.lm_top_k': '0 disables top‑K.',
      'label.lm_top_p': 'LM top‑P',
      'label.lm_negative_prompt': 'LM negative prompt',
      'help.lm_negative_prompt': 'Used when LM CFG is active.',
      'opt.use_constrained_decoding': 'Use constrained decoding (recommended)',
      'help.lm_inactive_notice': 'These settings only take effect when "Use LM" is enabled above.',

      'opt.use_cot_metas': 'CoT Metas',
      'help.use_cot_metas': 'Let the LM generate music metadata (BPM, key, etc.) via Chain-of-Thought.',
      'opt.use_cot_caption': 'CaptionRewrite',
      'help.use_cot_caption': 'Let the LM rewrite/format the caption (prompt) via Chain-of-Thought.',
      'opt.use_cot_language': 'CoT Language',
      'help.use_cot_language': 'Let the LM detect the vocal language via Chain-of-Thought.',
      'opt.parallel_thinking': 'ParallelThinking',
      'help.parallel_thinking': 'Process batch samples in parallel for faster LM planning (may use more VRAM).',
      'opt.constrained_decoding_debug': 'Constrained Decoding Debug',
      'help.constrained_decoding_debug': 'Enable debug info for constrained decoding (for troubleshooting).',
      'label.batch_size': 'Batch size',
      'label.audio_format': 'Audio format',
      'label.mp3_bitrate': 'MP3 bitrate',
      'label.mp3_sample_rate': 'MP3 sample rate',
      'label.score_sensitivity': 'Quality Score Sensitivity',
      'opt.auto_score': 'Auto score (after generation)',
      'label.inference_steps': 'Inference steps',
      'label.guidance_scale': 'Guidance scale',
      'label.shift': 'Shift',
      'label.infer_method': 'Inference method',
      'label.timesteps': 'Timesteps schedule',
      'label.source_start': 'Source start (Remix)',
      'label.source_end': 'Source end (Remix)',
      'opt.use_adg': 'Use ADG',
      'help.use_adg': 'ADG can improve stability for some prompts (experimental).',
      'label.cfg_start': 'CFG interval start',
      'label.cfg_end': 'CFG interval end',
      'opt.audio_normalization': 'Audio normalization',
      'label.normalization_db': 'Normalization (dB)',
      'label.latent_shift': 'Latent shift',
      'label.latent_rescale': 'Latent rescale',
      'label.audio_cover_strength': 'Audio cover strength',
      'label.cover_noise_strength': 'Cover noise strength',
      'label.cover_conditioning_balance': 'Cover conditioning balance',
      'label.chord_reference_renderer': 'Chord/reference renderer',
      'opt.chord_reference_renderer_soundfont': 'SoundFont (.sf2)',
      'opt.chord_reference_renderer_soundfont_named': 'SoundFont (.sf2): {name}',
      'opt.chord_reference_renderer_soundfont_unavailable': 'SoundFont (.sf2) — unavailable',
      'opt.chord_reference_renderer_internal': 'Internal synth',
      'help.advanced_note': 'Tip: leave most of these on defaults unless you know what you’re changing.',

      
      'title.lm_hints': '💡 LM codes hints',
      'label.lm_audio': 'Audio (for codes)',
      'label.audio_codes': 'Audio codes',
      'ph.audio_codes': 'Paste or generate audio codes here…',
      'btn.convert_audio_to_codes': 'Convert audio → codes',
      'btn.transcribe_codes': 'Transcribe codes',

      
      'title.import_json': '📥 Import JSON',
      'help.import_json': 'Import a JSON file produced by “Download JSON” to restore settings for a new run. The panel stays closed unless you open it.',
      'label.import_paste': 'Paste JSON',
      'ph.import_json': '{ "request": { ... } }',
      'help.import_paste': 'Paste the full JSON or only the request/payload block.',
      'label.import_file': 'JSON file (.json)',
      'help.import_file': 'Alternatively, choose a .json file from disk.',
      'btn.import_apply': 'Import',
      'status.no_file_selected': 'No file selected.',
      'status.import_ok': '✅ Imported settings',
      'status.import_error': '❌ Import error: {err}',
      'error.import_empty': '❌ Paste JSON or select a file first.',
      'error.import_no_request': 'Import: request/payload block not found in JSON.',

      
      'title.model_select': '🎚️ Choose DiT model',
      'help.model_select_desc': 'Select which DiT checkpoint to use for generation. Some models prioritize speed, others quality.',
      'model.base': 'Base (quality)',
      'model.sft': 'SFT (balanced)',
      'model.sft_turbo_ta_05': "SFT Turbo 0.5 (max quality)",
      'model.turbo': 'Turbo (fast)',
      'model.turbo_continuous': 'Turbo Continuous (fast and smooth)',
      'model.turbo_shift1': 'Turbo Shift 1 (fast, Shift 1)',
      'model.turbo_shift3': 'Turbo Shift 3 (fast, Shift 3)',

      
      'btn.generate': 'Generate',
      'btn.browse': 'Browse',
      'title.results': 'Results',
      'btn.download_json': 'Download JSON',
      'title.details': 'Details',

      
      'footer.service_offer': 'AceFlow by Marco Robustini - Your IP is:',
      'footer.songs_generated': 'Songs generated:',
      'footer.gpu_line': 'GPU: {name} — VRAM: {used}/{total} GB — Temp: {temp}°C',
      'help.model_shift_note': "The interface automatically adjusts the 'Shift' values according to the selected DiT model.",

      
      'status.ready': 'Ready. Model: {model}. Max duration: {max}s.',
      'status.server_not_ready': 'Server not ready.',
      'status.server_unreachable': 'Server unreachable.',
      'status.sending_request': 'Sending request… (LoRA: {lora})',
      'status.request_queued': 'Request queued. Position: {pos}.',
      'status.cant_read_job': 'Unable to read job status.',
      'status.queued_ahead': 'Queued. Jobs ahead: {pos}.',
      'status.running': 'Generating… please wait.',
      'status.error': 'Error: {msg}',
      'status.done_in': 'Completed in {sec}s.',
      'status.cancelled': 'Reservation cancelled.',
      'notice.queued_cancel_hint': 'Press Generate again to cancel the reservation.',

      
      'limit.queue_full': '🚦 Queue is busy (max {cap} active jobs). Please retry in a moment.',

      'error.request_failed': 'Request failed',
      'error.unknown': 'unknown',

      'upload.in_progress': 'Uploading…',
      'upload.done': 'Uploaded: {name}',
      'upload.error': 'Upload error: {msg}',
      'upload.failed': 'Upload failed',

      'lm.need_audio_first': 'Upload an audio file first in the “LM codes hints” section.',
      'lm.converting': 'Converting…',
      'lm.codes_generated': 'Codes generated.',
      'lm.paste_codes_first': 'Paste audio codes first.',
      'lm.transcribing': 'LM transcription in progress…',
      'lm.transcribe_not_available': 'Transcription is not available on this server.',
      'lm.transcribe_success': '✅ Analysis completed successfully.\nGenerated fields: {fields}',
      'lm.field_caption': 'prompt',
      'lm.field_lyrics': 'lyrics',
      'lm.field_bpm': 'BPM',
      'lm.field_duration': 'duration',
      'lm.field_keyscale': 'key / scale',
      'lm.field_language': 'vocal language',
      'lm.field_timesignature': 'time signature',
      'help.lm_codes_workflow': 'Use this section to analyze a song audio file with the LM engine. First convert the audio into audio codes, then transcribe those codes: the LM engine can automatically detect and fill the interface with style/prompt, lyrics, BPM, duration, key, major or minor mode, time signature, vocal language, and other musical clues.',

      'result.no_audio_found': 'No audio file found for this job (check server logs).',
      'result.audio_n': 'Audio {n}',
      'result.download_audio_n': 'Download audio {n}',

      'player.analyzing': 'Analyzing audio…',
      'player.web_audio_unavailable': 'WebAudio unavailable: using native player.',
      'player.web_audio_decode_failed': 'Waveform analysis failed in this browser. Using native playback.',
      'player.format_unsupported': 'Format not supported by this browser. Use Download to open it with an external player.',
      'player.stop': 'Stop',
      'player.skip_back': 'Back 5s',
      'player.skip_fwd': 'Forward 5s',
      'player.download': 'Download audio',
      'player.json': 'Download JSON',
      'player.mute': 'Mute',
      'player.unmute': 'Unmute',
      'player.file': 'File',
      'player.resolved_seed': 'Resolved seed',
      'help.generation_mode': 'Choose how to generate: Simple hides advanced controls; Custom exposes everything; Cover uses a reference song or codes; Remix uses uploaded source audio to create a remix version.',
      'help.random_from_archive': 'Fills the fields with a random example without changing the selected mode.',
      'label.ref_song_cover': 'Source song (Cover)',
      'label.ref_song_remix': 'Source song (Remix)',
      'help.ref_song_cover': 'Upload the source song used by the core Cover path. Both Cover noise strength and Audio cover strength affect how closely the result stays faithful to this source audio.',
      'help.ref_song_remix': 'Upload the source audio you want to remix. ACE-Step will generate a remix version guided by your caption and lyrics.',
      'help.style': 'Describe mood, genre, instruments, vocals, and any constraints. This is the main creative prompt.',
      'help.lyrics': 'Optional. Leave empty for instrumental. Keep lines short for better alignment.',
      'help.duration': 'Target length in seconds. If Auto is enabled, the server may choose a suitable duration.',
      'help.bpm': 'Optional tempo hint. Leave Auto if you do not care about a fixed BPM.',
      'help.seed': 'Controls randomness. Use -1 for random. Same seed + same settings = more repeatable results.',
      'help.seed_random': 'When enabled, a new random seed is used each run unless you set one manually.',
      'help.keyscale': 'Optional key/scale hint (e.g. C minor). Leave Auto if unknown.',
      'help.timesignature': 'Optional time signature (e.g. 4/4, 3/4). Leave Auto if unknown.',
      'help.vocal_language': 'Language of the sung voice. This is independent from the UI language.',
      'help.instrumental': 'Forces an instrumental track (no vocals), even if lyrics are provided.',
      'help.audio_format': 'Output format for the generated audio.',
      'help.mp3_bitrate': 'MP3 encoding bitrate. Default is 128 kbps for backward compatibility.',
      'help.mp3_sample_rate': 'MP3 encoding sample rate. Default is 48 kHz; 44.1 kHz is optional.',
      'help.score_sensitivity': 'Lower = more sensitive (default: 0.5). Adjusts how PMI maps to a normalized [0,1] quality score.',
      'help.auto_score': 'If enabled, the server computes PMI-based quality scores for each sample (requires LM audio codes). May add extra time.',
      'help.audio_codes': 'Low-level audio codes used by the LM tools. Only touch this if you know what you are doing.',
      'help.lora_select': 'Select a style LoRA (optional). A LoRA can bias timbre/style.',
      'help.lm_overview': 'These controls affect the Language Model that can generate/convert audio codes. Defaults are safe.',
      'help.advanced_overview': 'Advanced controls for diffusion/inference. Defaults are recommended unless you are tuning quality vs speed.',

      'help.inference_steps': 'Number of inference steps. More steps can improve quality but makes generation slower. Suggested: SFT/SFT Turbo 50 within a 1–200 range; other DiT models 8 within a 1–20 range.',
      'help.guidance_scale': 'Higher values follow text more closely.',
      'help.shift': 'Timestep shift factor for base models (range 1.0~5.0, default 3.0). Not effective for turbo models.',
      'help.infer_method': 'Diffusion inference method. ODE is the default; SDE can change the trajectory.',
      'help.timesteps': 'Comma-separated timestep values from 1.0 to 0.0. When set, they override the default step schedule.',
      'help.source_start': 'Optional start time in seconds for the source-audio window used by Remix.',
      'help.source_end': 'Optional end time in seconds for the Remix source window. Use -1 to continue until the end of the file.',
      'ph.timesteps': '0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0',
      'help.cfg_interval_start': 'Start of CFG interval (as a fraction of steps). Useful for stabilizing early steps.',
      'help.cfg_interval_end': 'End of CFG interval (as a fraction of steps). Useful for stabilizing late steps.',
      'help.cover_noise_strength': 'Controls how much Cover or Remix uses the source audio latents during noise initialization. It affects the renoise starting point, not the general strength of reference-audio conditioning.',
      'help.audio_cover_strength': 'Controls how strongly Cover/Remix follows the reference audio during denoising. Higher values keep the result closer to the source audio, while lower values allow more reinterpretation.',
      'help.cover_conditioning_balance': 'Visible only in Cover mode. 0.00 keeps only audio codes, 0.50 keeps both audio codes and source WAV, 1.00 keeps only the source WAV. Intermediate values keep both paths and are forwarded as metadata/debug guidance for the backend/model.',
      'help.chord_reference_renderer': 'Choose how generated chord/reference audio is rendered before code extraction or Cover conditioning.',
      'help.chord_reference_renderer_available': 'SoundFont rendering is available. Choose SoundFont for a more instrument-like reference, or Internal synth for the built-in renderer.',
      'help.chord_reference_renderer_available_named': 'SoundFont rendering is available via {name}. Choose SoundFont for a more instrument-like reference, or Internal synth for the built-in renderer.',
      'help.chord_reference_renderer_unavailable': 'No .sf2 SoundFont was found in AceFlow/soundfonts, so chord/reference audio will use the internal synth.',
      'help.latent_shift': 'Shift applied to DiT latents before VAE decode. Default 0 (no shift). Negative values (e.g. -0.04) can reduce clipping.',
      'help.latent_rescale': 'Rescale factor for DiT latents before VAE decode. Default 1.0 (no rescale). Values < 1.0 (e.g. 0.91) can reduce clipping.',
      'help.enable_normalization': 'Normalize audio volume to target peak level to prevent clipping or ensure consistent loudness.',
      'help.normalization_db': 'Target peak level in decibels. -1.0 dB is standard safe peak. -0.1 dB is max.',
      'help.batch_size': 'Number of audio to generate. Maximum 4.',
      'help.lm_temperature': '5Hz LM temperature (higher = more random).',
      'help.lm_cfg_scale': '5Hz LM CFG (1.0 = no CFG).',
      'help.lm_top_p': 'Top-P (1.0 = disabled).',
},

    it: {
      "sub.sampling.title": "Sampling",
      "sub.sampling.desc": "Controlli core: step, guidance e intervallo CFG.",
      "sub.quality.title": "Quality scoring",
      "sub.quality.desc": "Regola come le metriche qualità influenzano la selezione (se abilitate).",
      "sub.audio.title": "Post-processing audio",
      "sub.audio.desc": "Normalizzazione e controlli legati alla loudness.",
      "sub.latent.title": "Latent / VAE",
      "sub.latent.desc": "Shift e rescale dei latent prima della decodifica VAE.",
      "sub.output.title": "Output",
      "sub.output.desc": "Batch e formato audio.",
      
      'title.page': 'AceFlow',
      'ui.lang.label': 'Lingua UI:',
      'ui.lang.auto': 'Auto',
      'ui.lang.en': 'English',
      'ui.lang.it': 'Italiano',
      'auth.login.title': 'Accedi',
      'auth.login.help': 'Accedi per entrare nell’area protetta di ACE-Step e usare gli strumenti AceFlow.',
      'auth.kicker': 'Accesso protetto',
      'auth.hero.copy': 'Stai entrando nella workspace protetta di ACE-Step per generazione, remix e gestione LoRA.',
      'auth.hero.pill_music': 'Generazione musicale',
      'auth.hero.pill_remix': 'Workflow Remix',
      'auth.hero.pill_lora': 'LoRA pronta',
      'auth.hero.note': 'Usa il tuo account per continuare. Se stai entrando con una password temporanea, il sistema ti chiederà di cambiarla subito.',
      'auth.login.email': 'Email',
      'auth.login.password': 'Password',
      'auth.login.submit': 'Accedi',
      'auth.logout': 'Esci',
      'auth.admin.open': 'Utenti',
      'auth.change.title': 'Cambia password',
      'auth.change.help': 'Stai usando una password temporanea. Sostituiscila ora per sbloccare la workspace.',
      'auth.change.new_password': 'Nuova password',
      'auth.change.confirm_password': 'Conferma nuova password',
      'auth.change.submit': 'Salva password',
      'auth.status.login_failed': 'Accesso fallito: {msg}',
      'auth.status.password_changed': 'Password aggiornata. Ora puoi continuare.',
      'auth.status.password_change_failed': 'Cambio password fallito: {msg}',
      'auth.status.password_mismatch': 'Le due password non coincidono.',
      'auth.status.password_short': 'Usa almeno 10 caratteri.',
      'auth.status.session_required': 'Effettua l’accesso per continuare.',
      'auth.status.password_required': 'Cambia la password temporanea per continuare.',
      'auth.admin.title': 'Accesso utenti',
      'auth.admin.help': 'Crea utenti con password temporanea. Ogni account ha una sola sessione attiva vincolata all’IP di login.',
      'auth.admin.email': 'Email utente',
      'auth.admin.role': 'Ruolo',
      'auth.role.user': 'Utente',
      'auth.role.admin': 'Admin',
      'auth.admin.create': 'Crea utente',
      'auth.admin.temp_password': 'Password temporanea (mostrata una volta)',
      'auth.admin.user_list': 'Utenti esistenti',
      'auth.admin.audit_title': 'Eventi accesso recenti',
      'auth.admin.audit_empty': 'Nessun evento accesso per ora.',
      'auth.admin.created': 'Utente creato: {email}',
      'auth.admin.create_failed': 'Creazione utente fallita: {msg}',
      'auth.admin.list_failed': 'Impossibile caricare gli utenti: {msg}',
      'auth.admin.audit_failed': 'Impossibile caricare gli eventi accesso: {msg}',
      'auth.admin.no_users': 'Nessun utente trovato.',
      'auth.admin.must_change': 'Deve cambiare password',
      'auth.admin.last_login': 'Ultimo accesso',
      'auth.admin.delete': 'Elimina',
      'auth.admin.deleting': 'Eliminazione…',
      'auth.admin.deleted': 'Utente eliminato: {email}',
      'auth.admin.delete_failed': 'Eliminazione utente fallita: {msg}',
      'auth.admin.delete_confirm': "Eliminare l'utente {email}? Questa operazione non può essere annullata.",
      'auth.admin.delete_self_disabled': 'Sessione corrente',
      'auth.admin.reload_warning': 'refresh lista fallito; la UI mantiene il risultato locale della cancellazione',
      'auth.error.missing_email_or_password': 'Inserisci email e password.',
      'auth.error.invalid_credentials': 'Credenziali non valide.',
      'auth.error.password_too_short': 'Usa almeno 10 caratteri.',
      'auth.error.user_not_found': 'Utente non trovato.',
      'auth.error.invalid_email': 'Inserisci un indirizzo email valido.',
      'auth.error.user_already_exists': 'L’utente esiste già.',
      'auth.error.delete_self': 'Non puoi eliminare il tuo account.',
      'auth.error.delete_last_admin': 'Non puoi eliminare l’ultimo account admin.',
      'auth.error.admin_only': 'Solo admin.',
      'auth.error.auth_disabled': 'Autenticazione disabilitata.',
      'auth.event.ok': 'ok',
      'auth.event.fail': 'fallito',
      'auth.event.bootstrap_admin': 'Bootstrap admin',
      'auth.event.login': 'Login',
      'auth.event.logout': 'Logout',
      'auth.event.change_password': 'Cambio password',
      'auth.event.create_user': 'Creazione utente',
      'auth.event.delete_user': 'Eliminazione utente',
      'auth.event.session_ip_mismatch': 'Sessione invalidata (IP non corrispondente)',

      'title.generate_song': 'Genera canzone',
      'help.queue_info': 'La richiesta verrà messa in coda ed elaborata dal server.',
      'help.queue_ttl': 'Le canzoni generate restano disponibili sul server per la finestra di conservazione configurata, poi vengono eliminate automaticamente salvo cleanup disabilitato.',
      'label.generation_mode': '🎛️ Modalità',
      'mode.simple': 'Semplice',
      'mode.custom': 'Personalizzata',
      'mode.cover': 'Cover',
      'mode.remix': 'Remix',
      'btn.random_from_archive': 'Casuale da archivio',

      'label.ref_song': 'Brano di riferimento',
      'help.ref_song_upload': 'Carica un file audio quando usi Cover/Remix.',

      'label.style': '🎨 Stile / prompt',
      'ph.style': 'Descrivi stile, mood, strumenti…',
      'label.lyrics': '✍️ Testo (lyrics)',
      'ph.lyrics': 'Incolla qui il testo (o lascia vuoto per strumentale).',

      'label.duration_seconds': 'Durata (secondi)',
      'label.bpm': 'BPM',
      'ph.auto': '(auto)',
      'label.seed': 'Seed',
      'opt.auto': 'Auto',
      'opt.seed_random': 'Seed casuale',

      'label.key_scale': 'Tonalità / scala',
      'ph.key_scale': 'es. C major',
      'label.key_root': 'Tonalità',
      'label.key_mode': 'Modo',
      'opt.key_mode_major': 'Maggiore',
      'opt.key_mode_minor': 'Minore',
      'label.time_signature': 'Tempo',
      'label.vocal_language': 'Lingua vocale',

      'opt.instrumental': 'Strumentale (senza voce)',
      'opt.think_lm': 'Usa LM (assistente lyrics)',
      'help.think_lm': 'Se attivo, il server usa un modello linguistico per aiutare a scrivere/strutturare le lyrics e migliorare l\'allineamento.',

      
      'title.lora_style': 'Stile LoRA',
      'help.lora': 'Opzionale: applica un preset stile LoRA.',
      'label.select_lora': 'Seleziona LoRA',
      'label.lora_weight': 'Peso LoRA',
      'help.lora_weight': 'Più alto = influenza stile più forte.',
      'lora.loading': 'Caricamento…',
      'lora.none': '(Nessun LoRA)',
      'lora.none_short': 'nessuna',
      'opt.ab_compare': 'Genera confronto Audio 1 / Audio 2 (senza LoRA vs con LoRA)',
      'help.ab_compare': 'Genera due canzoni con lo stesso seed e gli stessi parametri. Il batch size viene ignorato e trattato come 1 quando il confronto A/B è attivo.',
      'ab.compare_title': 'Controlli Audio 1 / Audio 2',
      'ab.compare_desc': 'I player normali restano intatti. Questi controlli agiscono su entrambi insieme.',
      'ab.audio1': 'Audio 1',
      'ab.audio2': 'Audio 2',
      'ab.play_pause': 'Play/Pausa entrambi',
      'ab.stop': 'Stop entrambi',
      'ab.crossfade': 'Crossfade',
      'ab.batch_locked': 'Il batch size è bloccato a 1 mentre la modalità confronto è attiva.',

      
      'title.chord_progression': '🎼 Progressione accordi',
      'help.chord_progression': 'Definisci una progressione in numeri romani e applica un layer armonico pulito a stile, lyrics, tonalità e BPM senza toccare il contratto backend.',
      'label.chord_key': 'Tonalità',
      'help.chord_key': 'Nota fondamentale usata per risolvere la progressione romana in accordi reali.',
      'label.chord_scale': 'Scala',
      'help.chord_scale': 'Scegli il modo tonale usato per risolvere la progressione.',
      'label.chord_roman': 'Progressione romana',
      'help.chord_roman': 'Esempi: I - V - vi - IV, ii7 - V7 - Imaj7, i - bVII - bVI - V.',
      'ph.chord_roman': 'I - V - vi - IV',
      'label.chord_section_map': 'Override per sezione',
      'help.chord_section_map': 'Opzionale. Una regola per riga, per esempio Verse=I - vi - IV - V oppure Chorus: vi - IV - I - V. Le sezioni lyrics corrispondenti usano la propria progressione.',
      'ph.chord_section_map': 'Verse=I - vi - IV - V\nChorus=vi - IV - I - V',
      'opt.scale_major': 'Maggiore',
      'opt.scale_minor': 'Minore',
      'opt.chord_apply_keyscale': 'Applica tonalità/scala risolta',
      'help.chord_apply_keyscale': 'Scrive tonalità e scala risolte nel controllo Tonalità/Scala già esistente.',
      'opt.chord_apply_bpm': 'Mantieni il BPM attuale come manuale',
      'help.chord_apply_bpm': 'Quando applichi gli accordi, mantiene il BPM corrente e disattiva BPM Auto.',
      'opt.chord_apply_lyrics': 'Inietta tag accordi nelle lyrics',
      'help.chord_apply_lyrics': 'Applica i tag accordi alle intestazioni reali già presenti nelle lyrics. Se non trova sezioni supportate, aggiunge solo l\'header globale della progressione.',
      'label.chord_preview_resolved': 'Progressione risolta',
      'label.chord_preview_caption': 'Tag caption',
      'label.chord_preview_keyscale': 'Tag tonalità/scala',
      'label.chord_preview_sections': 'Mappa sezioni',
      'btn.chord_generate': 'Genera progressione sensata',
      'help.chord_generate': 'Crea una progressione romana sensata in base a tonalità e scala selezionate.',
      'btn.chord_auto_sections': 'Genera override sezioni',
      'help.chord_auto_sections': 'Legge le intestazioni supportate nelle lyrics e costruisce override per sezione con variazioni musicalmente plausibili a partire dalla progressione corrente.',
      'btn.chord_apply': 'Applica armonia',
      'help.chord_apply': 'Applica l\'armonia risolta a caption, tonalità/scala e lyrics senza cambiare modalità di generazione.',
      'btn.chord_apply_full': 'Applica armonia completa',
      'help.chord_apply_full_notice': 'Usa il riferimento armonico generato come audio codes in modalità Personalizzata, oppure come WAV puro in modalità Cover.',
      'btn.chord_remove': 'Azzera setup accordi',
      'help.chord_remove': 'Rimuove i tag accordi da caption e lyrics, azzera la progressione romana e gli override per sezione, e pulisce lo stato di chord conditioning della UI.',
      'status.chord_applied': 'Armonia applicata: {desc}',
      'status.chord_sections_applied': 'Override sezioni attivi: {count}.',
      'status.chord_sections_none': 'Solo progressione globale.',
      'status.chord_full_ready': 'Armonia completa pronta: riferimento armonico e audio code preparati per circa {duration}s e collegati al conditioning backend.',
      'status.chord_generated': 'Progressione generata: {roman}',
      'status.chord_sections_generated': 'Override per sezione generati dalla struttura attuale delle lyrics.',
      'status.chord_removed': 'Setup accordi azzerato da stile, lyrics, progressione e override per sezione.',
      'status.chord_full_cleared': 'Conditioning accordi rimosso da audio cover e codici audio.',
      'status.chord_full_uploading': 'Generazione audio di riferimento in corso…',
      'status.chord_full_extracting': 'Estrazione codici audio dal reference…',
      'error.chord_empty': 'Inserisci prima una progressione romana.',
      'error.chord_token_invalid': 'Token romano non valido: {token}',
      'error.chord_key_invalid': 'Tonalità accordi non valida.',
      'error.chord_full_failed': 'Armonia completa fallita: {msg}',
      'error.chord_section_line_invalid': 'Regola sezione non valida: {line}',
      'error.chord_sections_missing': 'Nessuna sezione lyrics supportata trovata per gli override automatici.',
      'title.advanced_settings': '🛠️ Impostazioni avanzate',
      'title.lm_settings': '🧠 Impostazioni LM',
      'help.lm_settings': 'Queste impostazioni controllano il Language Model 5Hz usato per pianificare e generare il testo/le lyrics.',
      'label.lm_temperature': 'Temperatura LM',
      'label.lm_cfg_scale': 'CFG LM',
      'label.lm_top_k': 'Top‑K LM',
      'help.lm_top_k': '0 disattiva il top‑K.',
      'label.lm_top_p': 'Top‑P LM',
      'label.lm_negative_prompt': 'Prompt negativo LM',
      'help.lm_negative_prompt': 'Usato quando la CFG del LM è attiva.',
      'opt.use_constrained_decoding': 'Usa constrained decoding (consigliato)',
      'help.lm_inactive_notice': 'Queste impostazioni hanno effetto solo quando "Usa LM" è attivo.',

      'opt.use_cot_metas': 'CoT Metas',
      'help.use_cot_metas': 'Permette al LM di generare i metadati musicali (BPM, tonalità, ecc.) via Chain-of-Thought.',
      'opt.use_cot_caption': 'CaptionRewrite',
      'help.use_cot_caption': 'Permette al LM di riscrivere/formattare la caption (prompt) via Chain-of-Thought.',
      'opt.use_cot_language': 'CoT Language',
      'help.use_cot_language': 'Permette al LM di rilevare la lingua vocale via Chain-of-Thought.',
      'opt.parallel_thinking': 'ParallelThinking',
      'help.parallel_thinking': 'Elabora i sample del batch in parallelo per un planning LM più veloce (può usare più VRAM).',
      'opt.constrained_decoding_debug': 'Constrained Decoding Debug',
      'help.constrained_decoding_debug': 'Abilita informazioni di debug per il constrained decoding (diagnostica).',
      'label.batch_size': 'Batch size',
      'label.audio_format': 'Formato audio',
      'label.mp3_bitrate': 'Bitrate MP3',
      'label.mp3_sample_rate': 'Frequenza MP3',
      'label.score_sensitivity': 'Sensibilità Quality Score',
      'opt.auto_score': 'Auto score (dopo la generazione)',
      'label.inference_steps': 'Step inferenza',
      'label.guidance_scale': 'Guidance scale',
      'label.shift': 'Shift',
      'label.infer_method': 'Metodo di inferenza',
      'label.timesteps': 'Schedule dei timesteps',
      'label.source_start': 'Inizio sorgente (Remix)',
      'label.source_end': 'Fine sorgente (Remix)',
      'opt.use_adg': 'Usa ADG',
      'help.use_adg': 'ADG può rendere la generazione più stabile in alcuni casi (sperimentale).',
      'label.cfg_start': 'CFG interval start',
      'label.cfg_end': 'CFG interval end',
      'opt.audio_normalization': 'Normalizzazione audio',
      'label.normalization_db': 'Normalizzazione (dB)',
      'label.latent_shift': 'Latent shift',
      'label.latent_rescale': 'Latent rescale',
      'label.audio_cover_strength': 'Audio cover strength',
      'label.cover_noise_strength': 'Cover noise strength',
      'label.cover_conditioning_balance': 'Bilanciamento conditioning Cover (0% codici ↔ 100% sorgente)',
      'label.chord_reference_renderer': 'Renderer audio accordi/reference',
      'opt.chord_reference_renderer_soundfont': 'SoundFont (.sf2)',
      'opt.chord_reference_renderer_soundfont_named': 'SoundFont (.sf2): {name}',
      'opt.chord_reference_renderer_soundfont_unavailable': 'SoundFont (.sf2) — non disponibile',
      'opt.chord_reference_renderer_internal': 'Synth interno',
      'help.advanced_note': 'Suggerimento: lascia i valori di default a meno che tu non sappia cosa stai cambiando.',

      
      'title.lm_hints': '💡 Suggerimenti codici LM',
      'label.lm_audio': 'Audio (per codici)',
      'label.audio_codes': 'Codici audio',
      'ph.audio_codes': 'Incolla o genera qui i codici audio…',
      'btn.convert_audio_to_codes': 'Converti audio → codici',
      'btn.transcribe_codes': 'Trascrivi codici',

      
      'title.import_json': '📥 Importa JSON',
      'help.import_json': 'Importa un file JSON prodotto da “Download JSON” per ripristinare i parametri e lanciare una nuova generazione. Il pannello resta chiuso finché non lo apri tu.',
      'label.import_paste': 'Incolla JSON',
      'ph.import_json': '{ "request": { ... } }',
      'help.import_paste': 'Puoi incollare il JSON completo oppure solo il blocco request/payload.',
      'label.import_file': 'File JSON (.json)',
      'help.import_file': 'In alternativa, seleziona un file .json dal disco.',
      'btn.import_apply': 'Importa',
      'status.no_file_selected': 'Nessun file selezionato.',
      'status.import_ok': '✅ Impostazioni importate',
      'status.import_error': '❌ Errore import: {err}',
      'error.import_empty': '❌ Incolla un JSON oppure seleziona un file.',
      'error.import_no_request': 'Import: blocco request/payload non trovato nel JSON.',

      
      'title.model_select': '🎚️ Scegli il modello DiT',
      'help.model_select_desc': 'Seleziona quale checkpoint DiT usare per la generazione. Alcuni modelli privilegiano la velocità, altri la qualità.',
      'model.base': 'Base — Qualità',
      'model.sft': 'SFT — Bilanciato',
      'model.sft_turbo_ta_05': "SFT Turbo 0.5 (massima qualit\u00e0)",
      'model.turbo': 'Turbo — Veloce',
      'model.turbo_continuous': 'Turbo Continuous — Veloce (più fluido)',
      'model.turbo_shift1': 'Turbo Shift 1 — Veloce (Shift 1)',
      'model.turbo_shift3': 'Turbo Shift 3 — Veloce (Shift 3)',

      
      'btn.generate': 'Genera',
      'btn.browse': 'Sfoglia',
      'title.results': 'Risultati',
      'btn.download_json': 'Scarica JSON',
      'title.details': 'Dettagli',

      
      'footer.service_offer': 'AceFlow by Marco Robustini - Il tuo IP è:',
      'footer.songs_generated': 'Canzoni generate:',
      'footer.gpu_line': 'GPU: {name} — VRAM: {used}/{total} GB — Temp: {temp}°C',
      'help.model_shift_note': "L'interfaccia adegua automaticamente i valori di 'Shift' in base al DiT selezionato.",

      
      'status.ready': 'Pronto. Modello: {model}. Durata max: {max}s.',
      'status.server_not_ready': 'Server non pronto.',
      'status.server_unreachable': 'Server non raggiungibile.',
      'status.sending_request': 'Invio richiesta… (LoRA: {lora})',
      'status.request_queued': 'Richiesta inserita in coda. Posizione: {pos}.',
      'status.cant_read_job': 'Impossibile leggere lo stato del job.',
      'status.queued_ahead': 'Generazione prenotata, elaborazioni in coda prima della tua: {pos}.',
      'status.running': 'Generazione in corso, attendere…',
      'status.error': 'Errore: {msg}',
      'status.done_in': 'Completato in {sec}s.',
      'status.cancelled': 'Prenotazione annullata.',
      'notice.queued_cancel_hint': 'Premi di nuovo Genera per annullare la prenotazione.',

      
      'limit.queue_full': '🚦 Coda piena (max {cap} job attivi). Riprova tra poco.',

      'error.request_failed': 'Errore nella richiesta',
      'error.unknown': 'sconosciuto',

      'upload.in_progress': 'Caricamento in corso…',
      'upload.done': 'Caricato: {name}',
      'upload.error': 'Errore upload: {msg}',
      'upload.failed': 'Caricamento fallito',

      'lm.need_audio_first': 'Carica prima un audio nella sezione “Suggerimenti codici LM”.',
      'lm.converting': 'Conversione in corso…',
      'lm.codes_generated': 'Codici generati.',
      'lm.paste_codes_first': 'Incolla prima dei codici audio.',
      'lm.transcribing': 'Trascrizione LM in corso…',
      'lm.transcribe_not_available': 'La trascrizione non è disponibile su questo server.',
      'lm.transcribe_success': '✅ Analisi completata con successo.\nCampi generati: {fields}',
      'lm.field_caption': 'prompt',
      'lm.field_lyrics': 'testo',
      'lm.field_bpm': 'BPM',
      'lm.field_duration': 'durata',
      'lm.field_keyscale': 'tonalità / scala',
      'lm.field_language': 'lingua vocale',
      'lm.field_timesignature': 'tempo musicale',
      'help.lm_codes_workflow': 'Usa questa sezione per analizzare il file audio di una canzone con il motore LM. Prima converti l\'audio in codici audio, poi trascrivi quei codici: il motore LM può rilevare e compilare automaticamente nell\'interfaccia stile/prompt, lyrics, BPM, durata, tonalità, modalità maggiore o minore, tempo musicale, lingua vocale e altri indizi musicali.',

      'result.no_audio_found': 'Nessun file audio trovato per questo job (controlla i log server).',
      'result.audio_n': 'Audio {n}',
      'result.download_audio_n': 'Scarica audio {n}',

      'player.analyzing': 'Analizzo audio…',
      'player.web_audio_unavailable': 'WebAudio non disponibile: uso il player nativo.',
      'player.web_audio_decode_failed': 'Analisi waveform non disponibile in questo browser. Uso riproduzione nativa.',
      'player.format_unsupported': 'Formato non supportato dal browser. Usa Download per aprirlo con un player esterno.',
      'player.stop': 'Stop',
      'player.skip_back': 'Indietro 5s',
      'player.skip_fwd': 'Avanti 5s',
      'player.download': 'Scarica audio',
      'player.json': 'Scarica JSON',
      'player.mute': 'Mute',
      'player.unmute': 'Unmute',
      'player.file': 'File',
      'player.resolved_seed': 'Seed risolto',
    
      'help.generation_mode': 'Scegli come generare: Simple nasconde i controlli avanzati; Custom mostra tutto; Cover usa una canzone di riferimento o i codes; Remix usa l’audio sorgente caricato per creare una versione remix.',
      'help.random_from_archive': 'Compila i campi con un esempio casuale senza cambiare la modalità selezionata.',
      'label.ref_song_cover': 'Canzone sorgente (Cover)',
      'label.ref_song_remix': 'Canzone sorgente (Remix)',
      'help.ref_song_cover': 'Carica la canzone sorgente usata dal ramo Cover del core. Sia Cover noise strength sia Audio cover strength influenzano quanto il risultato resta fedele a questo audio sorgente.',
      'help.ref_song_remix': 'Carica l’audio sorgente che vuoi remixare. ACE-Step genererà una versione remix guidata da caption e lyrics.',
      'help.style': 'Descrivi mood, genere, strumenti, voce e vincoli. Questo è il prompt creativo principale.',
      'help.lyrics': 'Opzionale. Lascia vuoto per strumentale. Righe brevi aiutano l’allineamento.',
      'help.duration': 'Durata target in secondi. Se Auto è attivo, il server può scegliere una durata adatta.',
      'help.bpm': 'Suggerimento di tempo (BPM) opzionale. Lascia Auto se non ti serve un BPM fisso.',
      'help.seed': 'Controlla la casualità. Usa -1 per casuale. Stesso seed + stesse impostazioni = risultati più ripetibili.',
      'help.seed_random': 'Se attivo, ogni run usa un seed casuale a meno che tu non lo imposti manualmente.',
      'help.keyscale': 'Suggerimento di tonalità/scala opzionale (es. C minor). Lascia Auto se non la conosci.',
      'help.timesignature': 'Suggerimento di tempo musicale (es. 4/4, 3/4). Lascia Auto se non ti serve.',
      'help.vocal_language': 'Lingua della voce cantata. È indipendente dalla lingua dell’interfaccia.',
      'help.instrumental': 'Forza un brano strumentale (senza voce), anche se inserisci lyrics.',
      'help.audio_format': 'Formato di output dell’audio generato.',
      'help.mp3_bitrate': 'Bitrate di codifica MP3. Default 128 kbps per retrocompatibilità.',
      'help.mp3_sample_rate': 'Frequenza di campionamento MP3. Default 48 kHz; 44.1 kHz è opzionale.',
      'help.score_sensitivity': 'Più basso = più sensibile (default: 0.5). Regola come la PMI viene mappata in uno score qualità normalizzato [0,1].',
      'help.auto_score': 'Se attivo, il server calcola automaticamente gli score qualità (PMI) per ogni sample (richiede i codici audio del LM). Può aumentare i tempi.',
      'help.audio_codes': 'Codici audio “low-level” usati dagli strumenti LM. Tocca solo se sai cosa stai facendo.',
      'help.lora_select': 'Seleziona una LoRA di stile (opzionale). Una LoRA può spostare timbro/stile.',
      'help.lm_overview': 'Questi controlli influenzano il Language Model che genera/converti i codici audio. I default sono sicuri.',
      'help.advanced_overview': 'Controlli avanzati per diffusione/inferenza. Consigliati i default se non stai ottimizzando qualità vs velocità.',

      'help.inference_steps': 'Numero di step di inferenza. Più step può aumentare la qualità ma rende la generazione più lenta. Consigliato: SFT/SFT Turbo 50 in un range 1–200; gli altri modelli DiT 8 in un range 1–20.',
      'help.guidance_scale': 'Valori più alti seguono il testo/prompt più da vicino.',
      'help.shift': 'Fattore di shift dei timestep per i modelli base (1.0–5.0, default 3.0). Non ha effetto sui modelli turbo.',
      'help.infer_method': 'Metodo di inferenza della diffusione. ODE è il default; SDE può cambiare la traiettoria.',
      'help.timesteps': 'Valori separati da virgola da 1.0 a 0.0. Se impostati, sovrascrivono la schedule standard degli step.',
      'help.source_start': 'Tempo di inizio opzionale, in secondi, della finestra di audio sorgente usata da Remix.',
      'help.source_end': 'Tempo di fine opzionale, in secondi, della finestra sorgente di Remix. Usa -1 per arrivare fino alla fine del file.',
      'ph.timesteps': '0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0',
      'help.cfg_interval_start': 'Inizio dell’intervallo CFG (frazione degli step). Utile per rendere più stabile l’inizio.',
      'help.cfg_interval_end': 'Fine dell’intervallo CFG (frazione degli step). Utile per rendere più stabile la fine.',
      'help.cover_noise_strength': "Controlla quanto Cover o Remix usano i latenti dell'audio sorgente durante l'inizializzazione del rumore. Influisce sul punto di partenza del renoise, non sulla forza generale del conditioning dell'audio di riferimento.",
      'help.audio_cover_strength': "Controlla quanto Cover/Remix seguono l'audio di riferimento durante il denoising. Valori più alti mantengono il risultato più vicino all'audio sorgente, mentre valori più bassi lasciano più spazio alla reinterpretazione.",
      'help.cover_conditioning_balance': 'Visibile solo in Cover mode. 0.00 mantiene solo gli audio codes, 0.50 mantiene sia audio codes sia WAV sorgente, 1.00 mantiene solo il WAV sorgente. I valori intermedi mantengono entrambi i path e vengono inoltrati come metadato/debug utile verso backend/modello.',
      'help.chord_reference_renderer': 'Scegli come generare l\'audio accordi/reference prima dell\'estrazione codici o del conditioning Cover.',
      'help.chord_reference_renderer_available': 'Il rendering SoundFont è disponibile. Scegli SoundFont per un reference più strumentale, oppure Synth interno per usare il renderer integrato.',
      'help.chord_reference_renderer_available_named': 'Il rendering SoundFont è disponibile tramite {name}. Scegli SoundFont per un reference più strumentale, oppure Synth interno per usare il renderer integrato.',
      'help.chord_reference_renderer_unavailable': 'Non è stato trovato alcun SoundFont .sf2 in AceFlow/soundfonts, quindi l\'audio accordi/reference userà il synth interno.',
      'help.latent_shift': 'Shift applicato ai latent DiT prima della decodifica VAE. Default 0. Valori negativi (es. -0.04) possono ridurre il clipping.',
      'help.latent_rescale': 'Fattore di rescale dei latent DiT prima della decodifica VAE. Default 1.0. Valori < 1.0 (es. 0.91) possono ridurre il clipping.',
      'help.enable_normalization': 'Normalizza il volume a un picco target per evitare clipping o avere loudness più consistente.',
      'help.normalization_db': 'Livello di picco target in dB. -1.0 dB è un valore “safe”; -0.1 dB è quasi massimo.',
      'help.batch_size': 'Numero di audio da generare. Massimo 4.',
      'help.lm_temperature': 'Temperatura del LM (più alta = più casuale).',
      'help.lm_cfg_scale': 'CFG del LM (1.0 = disattivato).',
      'help.lm_top_p': 'Top‑P (1.0 = disattivato).',
},
  };

  function detectBrowserLang() {
    const raw = (navigator.language || (navigator.languages && navigator.languages[0]) || '').toLowerCase();
    return raw.startsWith('it') ? 'it' : 'en';
  }

  function getUiLang() {
    try {
      const v = String(localStorage.getItem(STORAGE_KEY) || '').toLowerCase();
      if (v === 'en' || v === 'it') return v;
      
    } catch (e) {}
    return detectBrowserLang();
  }

  function getUiLangPref() {
    try {
      const v = String(localStorage.getItem(STORAGE_KEY) || '').toLowerCase();
      if (v === 'en' || v === 'it' || v === 'auto') return v;
    } catch (e) {}
    return 'auto';
  }

  function setUiLang(lang) {
    const v = String(lang || '').toLowerCase();
    try {
      if (v === 'en' || v === 'it') localStorage.setItem(STORAGE_KEY, v);
      else localStorage.setItem(STORAGE_KEY, 'auto');
    } catch (e) {}
    applyTranslations();
    try { window.dispatchEvent(new CustomEvent("ace:ui_lang_changed", { detail: { lang: getUiLang() } })); } catch (e) {}
  }

  function format(str, vars) {
    if (!vars) return str;
    return String(str).replace(/\{([a-zA-Z0-9_]+)\}/g, (m, k) => {
      return (vars[k] === undefined || vars[k] === null) ? '' : String(vars[k]);
    });
  }

  function t(key, vars) {
    const lang = getUiLang();
    const dict = I18N[lang] || I18N.en;
    const base = (dict && dict[key] != null) ? dict[key] : ((I18N.en && I18N.en[key] != null) ? I18N.en[key] : key);
    return format(base, vars);
  }

  function applyTranslations() {
    const lang = getUiLang();
    document.documentElement.lang = lang;
    document.title = t('title.page');

    document.querySelectorAll('[data-i18n]').forEach((node) => {
      const k = node.getAttribute('data-i18n');
      if (!k) return;
      node.textContent = t(k);
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
      const k = node.getAttribute('data-i18n-placeholder');
      if (!k) return;
      node.setAttribute('placeholder', t(k));
    });

    document.querySelectorAll('[data-i18n-title]').forEach((node) => {
      const k = node.getAttribute('data-i18n-title');
      if (!k) return;
      node.setAttribute('title', t(k));
    });

    document.querySelectorAll('[data-i18n-aria-label]').forEach((node) => {
      const k = node.getAttribute('data-i18n-aria-label');
      if (!k) return;
      node.setAttribute('aria-label', t(k));
    });

    
    const sel = document.getElementById('ui_lang_select');
    if (sel) {
      const pref = getUiLangPref();
      sel.value = pref;
    }

    try {
      window.dispatchEvent(new CustomEvent('ace_ui_lang_changed', { detail: { lang } }));
    } catch (e) {}
  }

  function bindLangSelector() {
    const sel = document.getElementById('ui_lang_select');
    if (!sel || sel.dataset.bound) return;
    sel.addEventListener('change', () => {
      setUiLang(sel.value);
    });
    sel.dataset.bound = '1';
  }

  
  window.ACE_I18N = I18N;
  window.detectBrowserLang = detectBrowserLang;
  window.getUiLang = getUiLang;
  window.setUiLang = setUiLang;
  window.t = t;
  window.applyTranslations = applyTranslations;

  
  document.addEventListener('DOMContentLoaded', () => {
    bindLangSelector();
    applyTranslations();
  });
})();
