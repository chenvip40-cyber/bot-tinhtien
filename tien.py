import discord
from discord.ext import commands
import re
from datetime import datetime
import json
import os
import io
from PIL import Image
from google import genai
import asyncio
from aiohttp import web

# =========================================================
# 0. KHỞI TẠO WEB SERVER GIẢ LẬP ĐỂ GIỮ PORT RENDER (24/7)
# =========================================================
async def handle_ping(request):
    return web.Response(text="Bot Discord đang hoạt động 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Web Server đã khởi chạy thành công trên Port {port}")

# =========================================================
# 1. CẤU HÌNH THÔNG TIN BOT & BACKUP
# =========================================================
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ĐÃ SỬA ID KÊNH BACKUP CỦA ANH VÀO ĐÂY DIRECTLY:
BACKUP_CHANNEL_ID = int(os.getenv('BACKUP_CHANNEL_ID', '1557240142953975930')) 

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = 'inventory_data.json'

# =========================================================
# 2. XỬ LÝ DỮ LIỆU JSON & BACKUP AUTOMATION
# =========================================================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "user_inventories" not in data:
                data["user_inventories"] = {}
            return data
    return {"inventory": {}, "prices": {}, "user_inventories": {}, "last_msg_id": None}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    # Tự động gửi backup lên Discord nếu có cấu hình kênh
    if bot.is_ready() and BACKUP_CHANNEL_ID != 0:
        bot.loop.create_task(backup_data_to_discord())

async def backup_data_to_discord():
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if channel and os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'rb') as f:
                await channel.send(
                    content=f"💾 **Auto-Backup Data** - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                    file=discord.File(f, DATA_FILE)
                )
        except Exception as e:
            print(f"❌ Lỗi Auto-Backup: {e}")

async def restore_data_from_discord():
    if BACKUP_CHANNEL_ID == 0:
        return
    await bot.wait_until_ready()
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=10):
            if msg.attachments:
                for att in msg.attachments:
                    if att.filename == DATA_FILE:
                        await att.save(DATA_FILE)
                        print("✅ Đã khôi phục dữ liệu kho từ kênh Backup Discord!")
                        return

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

def extract_member_name(message_content, author_name):
    match = re.search(r'(?:Tên|Ten)\s*:\s*([^\n\r]+)', message_content, re.IGNORECASE)
    if match:
        return match.group(1).strip().title()
    return author_name.strip().title()

# =========================================================
# 3. GIAO DIỆN EMBED TỒN KHO
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

def create_user_kho_embed(member_name, user_inventory, prices):
    now_str = datetime.now().strftime("%d/%m/%Y lúc %H:%M:%S")
    
    embed = discord.Embed(
        title=f"👤 SỔ VẬT TƯ CÁ NHÂN - {member_name.upper()}",
        description=f"⏱️ **Cập nhật:** `{now_str}`",
        color=discord.Color.blue()
    )
    
    total_val = 0
    items_list = []
    active_items = {k: v for k, v in user_inventory.items() if v > 0}
    
    if not active_items:
        embed.add_field(name="📦 Dữ liệu đóng góp", value="*(Chưa có vật tư ghi nhận)*", inline=False)
    else:
        for item, qty in sorted(active_items.items()):
            unit_p = prices.get(item, 0)
            item_v = unit_p * qty
            total_val += item_v
            
            val_str = f" ➔ `{item_v:,} VNĐ`" if unit_p > 0 else ""
            items_list.append(f"🔸 **{item}**: `x{qty}`{val_str}")
            
        embed.add_field(name="📦 Danh sách vật tư đã nhập", value="\n".join(items_list), inline=False)
        if total_val > 0:
            embed.add_field(name="💎 TỔNG GIÁ TRỊ ĐÓNG GÓP", value=f"```yaml\n{total_val:,} VNĐ\n```", inline=False)
            
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
    await start_web_server()
    await restore_data_from_discord()
    print(f'✅ Bot {bot.user.name} đã sẵn sàng phục vụ!')

@bot.command(name='checkkho')
async def check_kho_cmd(ctx):
    data = load_data()
    inventory = data.get("inventory", {})
    prices = data.get("prices", {})
    embed = create_kho_embed(inventory, prices)
    await ctx.send(embed=embed)

@bot.command(name='khocanhan', aliases=['mykho', 'khonguoidung'])
async def kho_ca_nhan_cmd(ctx, *, name: str = None):
    data = load_data()
    user_invs = data.get("user_inventories", {})
    prices = data.get("prices", {})
    
    target_name = name.strip().title() if name else ctx.author.display_name.strip().title()
    
    user_inv = user_invs.get(target_name, {})
    embed = create_user_kho_embed(target_name, user_inv, prices)
    await ctx.send(embed=embed)

@bot.command(name='bangkho')
async def bang_kho_cmd(ctx):
    data = load_data()
    user_invs = data.get("user_inventories", {})
    
    if not user_invs:
        await ctx.send("📋 Chưa có dữ liệu đóng góp kho cá nhân nào!")
        return

    embed = discord.Embed(
        title="📊 TỔNG HỢP KHO CÁ NHÂN THÀNH VIÊN",
        color=discord.Color.purple()
    )
    
    for user_name, inv in user_invs.items():
        items_summary = [f"{item}: `x{qty}`" for item, qty in inv.items() if qty > 0]
        val_text = ", ".join(items_summary) if items_summary else "*(Kho trống)*"
        embed.add_field(name=f"👤 {user_name}", value=val_text, inline=False)
        
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
    data["user_inventories"] = {}
    save_data(data)
    await update_kho_channel(ctx.guild)
    
    now_str = datetime.now().strftime("%d/%m/%Y lúc %H:%M:%S")
    embed = discord.Embed(
        title="🧹 XÁC NHẬN RESET KHO HÀNG & KHO CÁ NHÂN",
        description=f"Toàn bộ dữ liệu kho đã được đưa về **0**.",
        color=discord.Color.red()
    )
    embed.add_field(name="👤 Người thực hiện", value=ctx.author.mention, inline=True)
    embed.add_field(name="🕒 Thời điểm", value=f"`{now_str}`", inline=True)
    await ctx.send(embed=embed)

# =========================================================
# 6. TỰ ĐỘNG XỬ LÝ NHẬP / XUẤT
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
        user_inventories = data.setdefault("user_inventories", {})
        
        member_name = extract_member_name(message.content, message.author.display_name)
        user_inv = user_inventories.setdefault(member_name, {})
        
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
                            user_inv[item_name] = user_inv.get(item_name, 0) + qty
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
                    user_inv[item_name] = user_inv.get(item_name, 0) + qty
                    details.append(f"🟢 **+{qty}** {item_name}")

        if details:
            save_data(data)
            await message.add_reaction("✅")
            embed = discord.Embed(
                title="📥 XÁC NHẬN PHIẾU NHẬP KHO",
                color=discord.Color.green()
            )
            embed.add_field(name="👤 Người nhập kho", value=f"**{member_name}** ({message.author.mention})", inline=True)
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
if __name__ == '__main__':
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Lỗi: Chưa cấu hình DISCORD_TOKEN!")