from pathlib import Path
from datetime import datetime
from datasets import load_dataset
from unsloth import FastLanguageModel
from unsloth import FastModel
from unsloth.chat_templates import get_chat_template, train_on_responses_only
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig
from llama_cpp import Llama
import torch
from transformers import AutoTokenizer
from transformers import BitsAndBytesConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_PATH   = "training_data.jsonl"
BASE_MODEL  = "unsloth/gemma-3-27b-it-bnb-4bit"
SEQ_LEN     = 4096
BATCH_SIZE  = 4
GRAD_ACCUM  = 8
LR          = 2e-4
NUM_EPOCHS  = 3
DTYPE       = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

OUTPUT_DIR = Path(f"gemma3_ft").resolve()

RULES = """
id,name,rule
r1,Bare Metal Swap Usage Active,swap_used!=0
r2,Bare Metal Memory Exhausted,free<50
r3,Bare Metal Critical Memory Exhaustion,1min(free)<50
r4,Virtual Machine Memory Exhausted,free<50
r5,Virtual Machine Critical Memory Exhaustion,1min(free)<50
r6,Bare Metal Hugepages Depleted,pages_free==0
r7,Bare Metal CPU Overloaded,1min(idle_time)<=1
r8,Bare Metal CPU Critical Overload,5min(idle_time)<=1
r9,Virtual Machine CPU Overloaded,1min(idle_time)<=1
r10,Virtual Machine CPU Critical Overload,5min(idle_time)<=1
r11,Bare Metal Temperature Limit Reached,input_temp>=max_temp
r12,Bare Metal Critical Temperature Alert,input_temp>=critical_temp
r13,Bare Metal Critical Fan Speed,input_fanspeed<100
r14,Bare Metal Zombie Processes Active,zombie_count>0
r15,Virtual Machine SSH Access Down,ssh==0
r16,Bare Metal Network Critical: Default Gateway ARP Missing,(state=="up") and (gw_in_arp==0)
r17,Bare Metal Network Non-Standard MTU,(mtu!=1500) and (type==ether)
r18,Bare Metal Network Interface Flapping,1min(dynamicity(changes_count))>=6
r19,Bare Metal Network High Rx Errors,1min(dynamicity(rx_error))>100
r20,Bare Metal Network High Rx Packet Drops,1min(dynamicity(rx_drop))>10000
r21,Bare Metal Network High Tx Errors,1min(dynamicity(tx_error))>100
r22,Bare Metal Network High Tx Packet Loss (Tx Drops more than 100 per 1min),1min(dynamicity(tx_drop))>100
r23,Kernel/DPDK Network GSO Buffer Starvation,dynamicity(gso_no_buffers)>0
r24,Kernel/DPDK Network Mbuf Depletion,dynamicity(rx_no_buffer)>0
r25,Kernel/DPDK Network IP4 Input Buffer Missing,dynamicity(ip4_input_out_of_buffers)>0
r26,Kernel/DPDK Network Excessive IP Fragments,dynamicity(ip4_input_fragment_chain_too_long)>0
r27,Kernel/DPDK Network IP4 Destination Miss,dynamicity(ip4_input_destination_lookup_miss)>0
r28,Kernel/DPDK Network High Rx Errors,1min(dynamicity(rx_error))>100
r29,Kernel/DPDK Network High Rx Packet Drops,1min(dynamicity(rx_drop))>10000
r30,Kernel/DPDK Network High Tx Errors,1min(dynamicity(tx_error))>100
r31,Kernel/DPDK Network High Tx Packet Loss,1min(dynamicity(tx_drop))>100
r32,Kernel/DPDK Memory Low Buffers,(buffer_free/buffer_total)<0.1
r33,Kernel/DPDK Network DPDK Buffer Allocation Errors,dynamicity(dpdk_alloc_errors)>0
"""

INSTRUCTION = """
You are an expert system that suggests the most relevant monitoring rules for the user's request.
Return only IDs with a score between 0 and 1, separated by comma and descending order.
"""
                
            


logger.info("Loading dataset...")
ds = load_dataset("json", data_files=DATA_PATH, split="train")


def format_row(batch):
    formatted_texts = []
    for i in range(len(batch["input"])):
        formatted = (
            f"<start_of_turn>system\n{RULES}"
            f"<end_of_turn>\n"
            f"<start_of_turn>user\n{INSTRUCTION}\n{batch['input'][i]}"
            f"<end_of_turn>\n"
            f"<start_of_turn>model\n{batch['response'][i]}"
            f"<end_of_turn>\n"
        )
        formatted_texts.append(formatted)
    return {"text": formatted_texts}

ds = ds.map(format_row, batched=True)
logger.info(f"Dataset ready, ({len(ds)} examples)")



logger.info("Loading base model...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name          = BASE_MODEL,
    max_seq_length      = SEQ_LEN,
    load_in_4bit        = True,
    load_in_8bit        = False,
    full_finetuning     = False,
    device_map          = "auto"

)  

logger.info("Adding LoRA adapters...")
model = FastModel.get_peft_model(
    model,
    finetune_vision_layers     = False, # Turn off for just text!
    finetune_language_layers   = True,  # Should leave on!
    finetune_attention_modules = True,  # Attention good for GRPO
    finetune_mlp_modules       = True,  # SHould leave on always!

    r = 8,           # Larger = higher accuracy, but might overfit
    lora_alpha = 8,  # Recommended alpha == r at least
    lora_dropout = 0,
    bias = "none",
    random_state = 3407,
)

logger.info("Applying template")
tokenizer = get_chat_template(tokenizer, chat_template="gemma-3")

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = ds,
    eval_dataset = None, # Can set up evaluation!
    args = SFTConfig(
        dataset_text_field = "text",
        per_device_train_batch_size = BATCH_SIZE,
        gradient_accumulation_steps = GRAD_ACCUM, # Use GA to mimic batch size!
        warmup_steps = 5,
        num_train_epochs = NUM_EPOCHS, # Set this for 1 full training run.
        max_steps = 30,
        learning_rate = LR, # Reduce to 2e-5 for long training runs
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        report_to = "none", # Use this for WandB etc
        dataset_num_proc=2,
    ),
    output_dir      = str(OUTPUT_DIR / "logs") 
)

trainer = train_on_responses_only(
    trainer,
    instruction_part = "<start_of_turn>user\n",
    response_part = "<start_of_turn>model\n",
)

logger.info("Starting training...")
trainer_stats = trainer.train()
logger.info("Training finished.")
logger.info(f"{trainer_stats.metrics['train_runtime']} seconds used for training.")

OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
ADAPTER_DIR = OUTPUT_DIR / "lora"
FULL_DIR    = OUTPUT_DIR / "merged"
GGUF_DIR    = OUTPUT_DIR / "gguf"

logger.info("Saving LoRA adapter...")
model.save_pretrained(ADAPTER_DIR)
tokenizer.save_pretrained(ADAPTER_DIR)

model.save_pretrained_merged("gemma-3-finetune", tokenizer)


logger.info(f"Everything ready in: {OUTPUT_DIR}")

# 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