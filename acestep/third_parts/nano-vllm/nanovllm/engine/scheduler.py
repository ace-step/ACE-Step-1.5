from collections import deque

from nanovllm.config import Config
from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.engine.block_manager import BlockManager


class Scheduler:

    def __init__(self, config: Config):
        self.max_num_seqs = config.max_num_seqs
        self.max_num_batched_tokens = config.max_num_batched_tokens
        self.eos = config.eos
        self.block_manager = BlockManager(config.num_kvcache_blocks, config.kvcache_block_size)
        self.waiting: deque[Sequence] = deque()
        self.running: deque[Sequence] = deque()

    def is_finished(self):
        return not self.waiting and not self.running

    def add(self, seq: Sequence):
        self.waiting.append(seq)

    def schedule(self) -> tuple[list[Sequence], bool]:
        # prefill
        scheduled_seqs = []
        num_seqs = 0
        num_batched_tokens = 0
        processed_seqs = set()  # Track processed sequences to handle CFG pairs
        
        while self.waiting and num_seqs < self.max_num_seqs:
            seq = self.waiting[0]
            
            # For CFG sequences, ensure conditional and unconditional are scheduled together
            if seq.cfg_scale > 1.0 and seq.paired_seq is not None and not seq.is_unconditional:
                # This is a conditional sequence, need to schedule its paired unconditional sequence too
                paired_seq = seq.paired_seq
                if paired_seq.status != SequenceStatus.WAITING:
                    # Paired sequence not in waiting, skip this conditional sequence for now
                    break
                
                # Calculate tokens for both sequences
                total_tokens = (len(seq) - seq.num_cached_tokens) + (len(paired_seq) - paired_seq.num_cached_tokens)
                
                # FIX: Check if we have enough blocks for BOTH sequences combined
                # The old check was wrong: it checked each sequence independently,
                # but didn't account for the total blocks needed by both
                total_blocks_needed = seq.num_blocks + paired_seq.num_blocks
                can_allocate_both = len(self.block_manager.free_block_ids) >= total_blocks_needed
                
                if num_batched_tokens + total_tokens > self.max_num_batched_tokens or not can_allocate_both:
                    break
                
                # Schedule both sequences: conditional first, then unconditional
                for s in [seq, paired_seq]:
                    num_seqs += 1
                    self.block_manager.allocate(s)
                    num_batched_tokens += len(s) - s.num_cached_tokens
                    s.status = SequenceStatus.RUNNING
                    self.waiting.remove(s)
                    self.running.append(s)
                    scheduled_seqs.append(s)
                    processed_seqs.add(s.seq_id)
            else:
                # Normal sequence or unconditional sequence (already processed with its conditional)
                if seq.seq_id in processed_seqs:
                    # Skip if already processed as part of a CFG pair
                    self.waiting.popleft()
                    continue
                    
                if num_batched_tokens + len(seq) > self.max_num_batched_tokens or not self.block_manager.can_allocate(seq):
                    break
                num_seqs += 1
                self.block_manager.allocate(seq)
                num_batched_tokens += len(seq) - seq.num_cached_tokens
                seq.status = SequenceStatus.RUNNING
                self.waiting.popleft()
                self.running.append(seq)
                scheduled_seqs.append(seq)
                
        if scheduled_seqs:
            # For CFG batches, ensure conditional sequences come before their unconditional pairs
            cfg_cond_seqs = [s for s in scheduled_seqs if s.cfg_scale > 1.0 and not s.is_unconditional]
            cfg_uncond_seqs = [s for s in scheduled_seqs if s.is_unconditional]
            non_cfg_seqs = [s for s in scheduled_seqs if s.cfg_scale <= 1.0]
            
            # Reorder: non-CFG, then CFG conditional, then CFG unconditional
            scheduled_seqs = non_cfg_seqs + cfg_cond_seqs + cfg_uncond_seqs
            return scheduled_seqs, True

        # decode
        processed_seqs = set()
        temp_running = list(self.running)  # Work with a copy
        
        while temp_running and num_seqs < self.max_num_seqs:
            seq = temp_running.pop(0)
            
            # For CFG sequences, ensure conditional and unconditional are scheduled together
            if seq.cfg_scale > 1.0 and seq.paired_seq is not None and not seq.is_unconditional:
                paired_seq = seq.paired_seq
                if paired_seq not in temp_running:
                    # Paired sequence not available, skip for now
                    continue
                
                # Remove paired_seq from temp_running
                temp_running.remove(paired_seq)
                
                # FIX: Check if we have enough blocks for BOTH sequences to append
                # Each sequence needs 1 block when at block boundary (len % block_size == 1)
                block_size = self.block_manager.block_size
                blocks_needed_seq = 1 if len(seq) % block_size == 1 else 0
                blocks_needed_paired = 1 if len(paired_seq) % block_size == 1 else 0
                total_blocks_needed = blocks_needed_seq + blocks_needed_paired
                can_append_both = len(self.block_manager.free_block_ids) >= total_blocks_needed
                
                if not can_append_both:
                    # Try preempting other sequences
                    preempted = False
                    while not can_append_both and temp_running:
                        other_seq = temp_running.pop(0)
                        if other_seq != seq and other_seq != paired_seq:
                            self.preempt(other_seq)
                            # Recalculate with the same correct logic
                            can_append_both = len(self.block_manager.free_block_ids) >= total_blocks_needed
                            preempted = True
                        else:
                            temp_running.append(other_seq)
                            break
                    
                    if not can_append_both:
                        # Can't schedule this pair right now
                        temp_running.append(seq)
                        temp_running.append(paired_seq)
                        continue
                
                # Schedule both sequences
                for s in [seq, paired_seq]:
                    num_seqs += 1
                    self.block_manager.may_append(s)
                    scheduled_seqs.append(s)
                    processed_seqs.add(s.seq_id)
                    # Remove from actual running list if scheduled
                    if s in self.running:
                        self.running.remove(s)
            else:
                # Normal sequence or unconditional (already processed)
                if seq.seq_id in processed_seqs:
                    continue
                    
                while not self.block_manager.can_append(seq):
                    if temp_running:
                        other_seq = temp_running.pop(0)
                        if other_seq != seq:
                            self.preempt(other_seq)
                        else:
                            temp_running.append(other_seq)
                            break
                    else:
                        self.preempt(seq)
                        if seq in self.running:
                            self.running.remove(seq)
                        break
                else:
                    num_seqs += 1
                    self.block_manager.may_append(seq)
                    scheduled_seqs.append(seq)
                    if seq in self.running:
                        self.running.remove(seq)
                    
        if not scheduled_seqs:
            # No sequences could be scheduled - provide informative error
            waiting_count = len(self.waiting)
            running_count = len(self.running)
            free_blocks = len(self.block_manager.free_block_ids)
            total_blocks = len(self.block_manager.blocks)

            if waiting_count > 0:
                seq = self.waiting[0]
                blocks_needed = seq.num_blocks
                prompt_tokens = len(seq)
                if seq.cfg_scale > 1.0 and seq.paired_seq is not None:
                    blocks_needed += seq.paired_seq.num_blocks
                    prompt_tokens = f"{len(seq)}+{len(seq.paired_seq)}"
                raise RuntimeError(
                    f"Insufficient KV cache to schedule sequence. "
                    f"Free blocks: {free_blocks}/{total_blocks}, blocks needed: {blocks_needed}, "
                    f"prompt tokens: {prompt_tokens}, block size: {self.block_manager.block_size}. "
                    f"The prompt may be too long for available GPU memory, or gpu_memory_utilization is too low."
                )
            else:
                raise RuntimeError(
                    f"No schedulable sequences found. "
                    f"Waiting: {waiting_count}, Running: {running_count}, "
                    f"Free blocks: {free_blocks}/{total_blocks}"
                )

        # For CFG batches in decode, ensure conditional sequences come before unconditional
        cfg_cond_seqs = [s for s in scheduled_seqs if s.cfg_scale > 1.0 and not s.is_unconditional]
        cfg_uncond_seqs = [s for s in scheduled_seqs if s.is_unconditional]
        non_cfg_seqs = [s for s in scheduled_seqs if s.cfg_scale <= 1.0]
        scheduled_seqs = non_cfg_seqs + cfg_cond_seqs + cfg_uncond_seqs
        
        self.running.extendleft(reversed(scheduled_seqs))
        return scheduled_seqs, False

    def preempt(self, seq: Sequence):
        seq.status = SequenceStatus.WAITING
        self.block_manager.deallocate(seq)
        self.waiting.appendleft(seq)

    def postprocess(self, seqs: list[Sequence], token_ids: list[int]) -> list[bool]:
        # Check if this is a CFG batch
        is_cfg_batch = False
        if len(seqs) > 0 and seqs[0].cfg_scale > 1.0 and seqs[0].paired_seq is not None:
            num_cond = len(seqs) // 2
            is_cfg_batch = (num_cond > 0 and 
                           not seqs[0].is_unconditional and 
                           seqs[num_cond].is_unconditional)
        
        if is_cfg_batch:
            # CFG batch: seqs = [cond_seq1, cond_seq2, ..., uncond_seq1, uncond_seq2, ...]
            # token_ids correspond to conditional sequences only (sampled from CFG logits)
            num_cond = len(seqs) // 2
            cond_seqs = seqs[:num_cond]
            uncond_seqs = seqs[num_cond:]
            
            # Apply the same sampled token to both conditional and unconditional sequences
            for i, (cond_seq, uncond_seq, token_id) in enumerate(zip(cond_seqs, uncond_seqs, token_ids)):
                cond_seq.append_token(token_id)
                uncond_seq.append_token(token_id)  # Same token for unconditional
                
                # Check if either sequence is finished
                cond_finished = ((not cond_seq.ignore_eos and token_id == self.eos) or 
                                cond_seq.num_completion_tokens == cond_seq.max_tokens)
                uncond_finished = ((not uncond_seq.ignore_eos and token_id == self.eos) or 
                                  uncond_seq.num_completion_tokens == uncond_seq.max_tokens)
                
                if cond_finished or uncond_finished:
                    # Mark both as finished
                    cond_seq.status = SequenceStatus.FINISHED
                    uncond_seq.status = SequenceStatus.FINISHED
                    self.block_manager.deallocate(cond_seq)
                    self.block_manager.deallocate(uncond_seq)
                    if cond_seq in self.running:
                        self.running.remove(cond_seq)
                    if uncond_seq in self.running:
                        self.running.remove(uncond_seq)
        else:
            # Normal batch
            for seq, token_id in zip(seqs, token_ids):
                seq.append_token(token_id)
                if (not seq.ignore_eos and token_id == self.eos) or seq.num_completion_tokens == seq.max_tokens:
                    seq.status = SequenceStatus.FINISHED
                    self.block_manager.deallocate(seq)
                    self.running.remove(seq)
