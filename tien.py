import discord
from discord.ext import commands
import re
from datetime import datetime
import json
import os
import io
from PIL import Image
from google import genai

# =========================================================
# 1. CẤU HÌNH THÔNG TIN BOT
# =========================================================
TOKEN = 'TOKEN_BOT_DISCORD_CỦA_BẠN'
GEMINI_API_KEY = 'API_KEY_GEMINI_CỦA_BẠN'

client = None
if GEMINI_API_KEY and GEMINI_API_KEY != 'API_KEY_GEMINI_CỦA_BẠN':
    client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = 'inventory_data.json'

# =========================================================
# 2. XỬ LÝ DỮ LIỆU JSON & ĐỔI GIÁ
# =========================================================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"inventory": {}, "prices": {}, "last_msg_id": None}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def parse_price(price_str):
    price_str = price_str.lower().strip()
    match = re.match(r'^(\d+)(k)?(\d+)?$', price_str)
    if match:
        main = int(match.group(1))
        has_k = match.group(2)
        dec = match.group(3)
        if has_k:
            if dec:
                return main * 1000 + int(dec) * 100
            return main * 1000
        return main
    return 0

# =========================================================
# 3. GIAO DIỆN EMBED TỒN KHO (CÓ NGÀY GIỜ CHÍNH XÁC)
# =========================================================
def create_kho_embed(inventory, prices):
    now_str = datetime.now().strftime("%d/%m/%Y lúc %H:%M:%S")
    
    embed = discord.Embed(
        title="📦 BÁO CÁO TỒN KHO TỔNG - HKT",
        description=f"⏱️ **Thời gian cập nhật:** `{now_str}`",
        color=discord.Color.gold()
    )
    
    total_value = 0
    items_list = []
    low_stock_list = []

    active_items = {k: v for k, v in inventory.items() if v > 0}

    if not active_items:
        embed.add_field(name="📋 Danh Sách Vật Tư", value="*(Kho hiện đang trống)*", inline=False)
    else:
        for item, qty in sorted(active_items.items()):
            price_unit = prices.get(item, 0)
            item_val = price_unit * qty
            total_value += item_val
            
            price_str = f"{price_unit:,}đ/cái" if price_unit > 0 else "Chưa định giá"
            val_str = f" ➔ **{item_val:,} VNĐ**" if price_unit > 0 else ""
            
            items_list.append(f"🔹 **{item}**: `x{qty}` | Giá niêm yết: *{price_str}*{val_str}")
            
            if qty <= 5:
                low_stock_list.append(f"⚠️ **{item}** (Chỉ còn `{qty}` cái)")

        embed.add_field(
            name="📋 Danh Sách Tồn Kho & Giá Trị", 
            value="\n".join(items_list), 
            inline=False
        )

    embed.add_field(
        name="💰 TỔNG TRỊ GIÁ KHO HÀNG", 
        value=f"```fix\n💵 {total_value:,} VNĐ\n```", 
        inline=False
    )
    
    if low_stock_list:
        embed.add_field(
            name="🚨 CẢNH BÁO TỒN KHO THẤP (≤ 5)", 
            value="\n".join(low_stock_list), 
            inline=False
        )
        
    embed.set_footer(text="Hệ Thống Quản Lý Vật Tư Minh Bạch • HKT", icon_url="https://cdn-icons-png.flaticon.com/512/2897/2897785.png")
    return embed

# =========================================================
# 4. TỰ ĐỘNG CẬP NHẬT KÊNH
# =========================================================
async def update_prices_from_channel(guild):
    price_channel = discord.utils.get(guild.text_channels, name='gia-san-pham')
    if not price_channel:
        return

    data = load_data()
    prices = data.get("prices", {})

    async for msg in price_channel.history(limit=20):
        matches = re.findall(r'([A-ZÀ-Ỹa-zà-ỹ\s]+?)\s+(\d+k?\d*)\b', msg.content)
        for item, price in matches:
            item_name = item.strip().title()
            prices[item_name] = parse_price(price)

    data["prices"] = prices
    save_data(data)

async def update_kho_channel(guild):
    kho_channel = discord.utils.get(guild.text_channels, name='kho')
    if not kho_channel:
        return

    data = load_data()
    inventory = data.get("inventory", {})
    prices = data.get("prices", {})

    embed = create_kho_embed(inventory, prices)
    msg_id = data.get("last_msg_id")

    if msg_id:
        try:
            msg = await kho_channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    new_msg = await kho_channel.send(embed=embed)
    data["last_msg_id"] = new_msg.id
    save_data(data)

# =========================================================
# 5. LỆNH GÕ TRỰC TIẾP
# =========================================================
@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user.name} đã sẵn sàng phục vụ!')

@bot.command(name='checkkho')
async def check_kho_cmd(ctx):
    data = load_data()
    inventory = data.get("inventory", {})
    prices = data.get("prices", {})
    embed = create_kho_embed(inventory, prices)
    await ctx.send(embed=embed)

@bot.command(name='capnhatgia')
async def cap_nhat_gia_cmd(ctx):
    await update_prices_from_channel(ctx.guild)
    await update_kho_channel(ctx.guild)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    await ctx.send(f"✅ **Đã cập nhật lại toàn bộ bảng giá lúc `{now_str}`!**")

@bot.command(name='resetkho')
@commands.has_permissions(administrator=True)
async def reset_kho_cmd(ctx):
    data = load_data()
    data["inventory"] = {}
    save_data(data)
    await update_kho_channel(ctx.guild)
    
    now_str = datetime.now().strftime("%d/%m/%Y lúc %H:%M:%S")
    embed = discord.Embed(
        title="🧹 XÁC NHẬN RESET KHO HÀNG",
        description=f"Toàn bộ dữ liệu tồn kho đã được đưa về **0**.",
        color=discord.Color.red()
    )
    embed.add_field(name="👤 Người thực hiện", value=ctx.author.mention, inline=True)
    embed.add_field(name="🕒 Thời điểm", value=f"`{now_str}`", inline=True)
    await ctx.send(embed=embed)

@reset_kho_cmd.error
async def reset_kho_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bạn cần có quyền **Quản trị viên (Admin)** để thực hiện lệnh này!")

# =========================================================
# 6. TỰ ĐỘNG XỬ LÝ NHẬP / XUẤT (KÈM NGÀY GIỜ BÁO CÁO)
# =========================================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    channel_name = message.channel.name
    now_str = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")

    # 1. KÊNH GIÁ SẢN PHẨM (#gia-san-pham)
    if channel_name == 'gia-san-pham':
        await update_prices_from_channel(message.guild)
        await update_kho_channel(message.guild)
        await message.add_reaction("🏷️")

    # 2. KÊNH NHẬP KHO (#vat-tu-hom-nay)
    elif channel_name == 'vat-tu-hom-nay':
        data = load_data()
        inventory = data.setdefault("inventory", {})
        details = []

        if message.attachments and client:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    await message.add_reaction("🔍")
                    image_bytes = await attachment.read()
                    img = Image.open(io.BytesIO(image_bytes))
                    prompt = "Liệt kê chính xác số lượng vật tư trong ảnh túi đồ theo định dạng: x[số] [Tên vật tư]"
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[prompt, img]
                        )
                        parsed_items = re.findall(r"x(\d+)\s+(.+)", response.text)
                        for qty, item_name in parsed_items:
                            qty = int(qty)
                            item_name = item_name.strip().title()
                            inventory[item_name] = inventory.get(item_name, 0) + qty
                            details.append(f"🟢 **+{qty}** {item_name}")
                    except Exception as e:
                        await message.reply(f"❌ Lỗi quét ảnh: {e}")
        else:
            items = re.findall(r"x(\d+)\s+(.+)", message.content)
            if items:
                for qty, item_name in items:
                    qty = int(qty)
                    item_name = item_name.strip().title()
                    inventory[item_name] = inventory.get(item_name, 0) + qty
                    details.append(f"🟢 **+{qty}** {item_name}")

        if details:
            save_data(data)
            await message.add_reaction("✅")
            embed = discord.Embed(
                title="📥 XÁC NHẬN PHIẾU NHẬP KHO",
                color=discord.Color.green()
            )
            embed.add_field(name="👤 Người thực hiện", value=message.author.mention, inline=True)
            embed.add_field(name="🕒 Thời gian", value=f"`{now_str}`", inline=True)
            embed.add_field(name="📦 Chi tiết vật tư", value="\n".join(details), inline=False)
            await message.reply(embed=embed)
            await update_prices_from_channel(message.guild)
            await update_kho_channel(message.guild)

    # 3. KÊNH BÁN SẢN PHẨM / TRỪ KHO (#ban-san-pham)
    elif channel_name == 'ban-san-pham':
        data = load_data()
        inventory = data.setdefault("inventory", {})
        prices = data.get("prices", {})
        items = re.findall(r"x(\d+)\s+(.+)", message.content)
        
        details = []
        errors = []
        total_earned = 0

        if items:
            for qty, item_name in items:
                qty = int(qty)
                item_name = item_name.strip().title()
                current_qty = inventory.get(item_name, 0)

                if current_qty < qty:
                    errors.append(f"❌ **{item_name}**: Kho còn `{current_qty}`, không đủ xuất `{qty}`!")
                else:
                    inventory[item_name] = current_qty - qty
                    unit_p = prices.get(item_name, 0)
                    earned = unit_p * qty
                    total_earned += earned
                    
                    price_note = f" *(Thu: {earned:,}đ)*" if unit_p > 0 else ""
                    details.append(f"🔴 **-{qty}** {item_name} {price_note} | Tồn kho mới: `{inventory[item_name]}`")

            if details:
                save_data(data)
                await message.add_reaction("💸")
                embed = discord.Embed(
                    title="📤 XÁC NHẬN PHIẾU XUẤT BÁN KHO",
                    color=discord.Color.orange()
                )
                embed.add_field(name="👤 Người thực hiện", value=message.author.mention, inline=True)
                embed.add_field(name="🕒 Thời gian", value=f"`{now_str}`", inline=True)
                embed.add_field(name="📦 Chi tiết xuất kho", value="\n".join(details), inline=False)
                
                if total_earned > 0:
                    embed.add_field(
                        name="💵 TỔNG TIỀN THU VỀ", 
                        value=f"```yaml\n+ {total_earned:,} VNĐ\n```", 
                        inline=False
                    )
                if errors:
                    embed.add_field(name="⚠️ Lỗi tồn kho", value="\n".join(errors), inline=False)
                    
                await message.reply(embed=embed)
                await update_prices_from_channel(message.guild)
                await update_kho_channel(message.guild)
            elif errors:
                await message.reply("\n".join(errors))

    # 4. KÊNH CHECK KHO (#check-kho)
    elif channel_name == 'check-kho':
        if not message.content.startswith('!'):
            data = load_data()
            inventory = data.get("inventory", {})
            prices = data.get("prices", {})
            embed = create_kho_embed(inventory, prices)
            await message.reply(embed=embed)

# =========================================================
# 7. KHỞI CHẠY BOT
# =========================================================
bot.run('MTU1NzE4NDg1NjQyNzk5MTE4MQ.GYqNyk.yoS9AxaubO7jfSYunI1n3g7H242rDkhiA4Uvm8')