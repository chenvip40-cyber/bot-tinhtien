import discord
from discord.ext import commands
import re
from datetime import datetime
import json
import os
import io
import sys
import asyncio
from PIL import Image
from google import genai
from aiohttp import web

# Ép Python đẩy log stdout ngay lập tức lên Dashboard Render
sys.stdout.reconfigure(line_buffering=True)

# =========================================================
# 0. KHỞI TẠO WEB SERVER GIẢ LẬP ĐỂ GIỮ PORT RENDER (24/7)
# =========================================================
async def handle_ping(request):
    return web.Response(text="Bot Discord đang hoạt động 24/7 trên Render!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Web Server đã lắng nghe thành công trên Port {port}")

# =========================================================
# 1. CẤU HÌNH THÔNG TIN BOT & BACKUP
# =========================================================
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
BACKUP_CHANNEL_ID = int(os.getenv('BACKUP_CHANNEL_ID', '1557240142953975930')) 

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Đã khởi tạo Gemini API Client thành công!")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo Gemini API Client: {e}")
else:
    print("⚠️ CẢNH BÁO: Chưa cấu hình GEMINI_API_KEY trong Environment!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = 'inventory_data.json'

GTA5_INVENTORY_PROMPT = """
Bạn là hệ thống kiểm đếm túi đồ trong game GTA5 Roleplay.
Hãy nhìn vào từng ô vật phẩm trong ảnh túi đồ và liệt kê chính xác TÊN VẬT PHẨM cùng SỐ LƯỢNG.

Quy tắc phân tích từng ô:
1. SỐ LƯỢNG: Chỉ lấy con số nguyên nằm ở GÓC DƯỚI BÊN PHẢI mỗi ô (Ví dụ: 7, 24, 31, 16). Tuyệt đối BỎ QUA con số trọng lượng có chữ 'kg' hoặc con số ở góc trên bên trái (như 3.50, 12.00, 15.50, 8.00). Nếu không thấy số lượng ở góc dưới thì mặc định là 1.
2. TÊN VẬT PHẨM (Đọc chữ ghi trên ô hoặc phân biệt theo biểu tượng/màu sắc):
   - Nếu ô có ghi chữ rõ ràng (như "Đá thô", "Quặng sắt", "Quặng vàng", "Quặng bạc", "Quặng đồng", "Quặng thiếc"): Lấy đúng tên đó.
   - Thỏi màu vàng kim / vàng sáng: Thỏi vàng
   - Thỏi màu xám mịn / thép: Thỏi sắt
   - Thỏi màu đồng / cam đỏ: Thỏi đồng
   - Thỏi màu bạc sáng / nhám: Thỏi bạc
   - Thỏi màu xám bạc thô: Thỏi thiếc
   - Cục đá màu vàng: Quặng vàng
   - Cục đá màu đỏ / nâu: Quặng sắt
   - Cục đá màu trắng / bạc: Quặng bạc
   - Cục đá màu xám / đen: Đá thô
   - Cục đá màu đồng: Quặng đồng
   - Viên kim cương lấp lánh: Kim Cương

Yêu cầu đầu ra:
Chỉ trả về danh sách theo đúng cú pháp (mỗi món 1 dòng, tuyệt đối KHÔNG thêm lời chào hay giải thích):
x[số lượng] [Tên vật phẩm]

Ví dụ:
x7 Thỏi vàng
x24 Thỏi sắt
x31 Thỏi đồng
x16 Thỏi bạc
"""

# =========================================================
# 2. XỬ LÝ DỮ LIỆU JSON & BACKUP AUTOMATION
# =========================================================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "user_inventories" not in data:
                    data["user_inventories"] = {}
                return data
        except Exception as e:
            print(f"❌ Lỗi đọc file JSON: {e}")
    return {"inventory": {}, "prices": {}, "user_inventories": {}, "last_msg_id": None}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
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
    await restore_data_from_discord()
    print(f'✅ Bot {bot.user.name} (ID: {bot.user.id}) đã kết nối thành công!')

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
    prices = data.get("prices", {})
    
    if not user_invs:
        await ctx.send("📋 Chưa có dữ liệu đóng góp kho cá nhân nào!")
        return

    total_guild_val = 0
    user_vals = {}
    for member, items in user_invs.items():
        m_val = sum(qty * prices.get(k, 0) for k, qty in items.items())
        user_vals[member] = m_val
        total_guild_val += m_val

    embed = discord.Embed(
        title="📊 TỔNG HỢP KHO CÁ NHÂN THÀNH VIÊN",
        color=discord.Color.purple()
    )
    
    for user_name, inv in user_invs.items():
        items_summary = [f"**{item}**: `x{qty}`" for item, qty in inv.items() if qty > 0]
        val_text = ", ".join(items_summary) if items_summary else "*(Đã xuất bán hết)*"
        
        m_val = user_vals.get(user_name, 0)
        pct = (m_val / total_guild_val * 100) if total_guild_val > 0 else 0
        price_note = f"\n💰 Quy đổi: **{m_val:,} VNĐ** *({pct:.1f}% tổng kho)*" if m_val > 0 else ""
        
        embed.add_field(name=f"👤 {user_name}", value=f"{val_text}{price_note}", inline=False)
        
    embed.set_footer(text=f"💵 Tổng giá trị đóng góp toàn team: {total_guild_val:,} VNĐ")
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

        if message.attachments:
            if not client:
                await message.reply("❌ Bot chưa được cấu hình `GEMINI_API_KEY` để quét ảnh túi đồ!")
                return

            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    await message.add_reaction("🔍")
                    image_bytes = await attachment.read()
                    img = Image.open(io.BytesIO(image_bytes))
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[GTA5_INVENTORY_PROMPT, img]
                        )
                        parsed_items = re.findall(r"x(\d+)\s+(.+)", response.text, re.IGNORECASE)
                        for qty, item_name in parsed_items:
                            qty = int(qty)
                            item_name = item_name.strip().title()
                            
                            inventory[item_name] = inventory.get(item_name, 0) + qty
                            user_inv[item_name] = user_inv.get(item_name, 0) + qty
                            details.append(f"🟢 **+{qty}** {item_name}")
                    except Exception as e:
                        print(f"❌ Lỗi Gemini OCR: {e}")
                        await message.reply(f"❌ Lỗi nhận diện ảnh túi đồ: `{e}`")
        else:
            items = re.findall(r"x(\d+)\s+(.+)", message.content, re.IGNORECASE)
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
        user_inventories = data.setdefault("user_inventories", {})
        prices = data.get("prices", {})
        items = re.findall(r"x(\d+)\s+(.+)", message.content, re.IGNORECASE)
        
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
                    
                    needed_to_deduct = qty
                    deduct_logs = []

                    for u_name, u_inv in list(user_inventories.items()):
                        if item_name in u_inv and u_inv[item_name] > 0:
                            take = min(needed_to_deduct, u_inv[item_name])
                            u_inv[item_name] -= take
                            needed_to_deduct -= take
                            
                            remains = u_inv[item_name]
                            deduct_logs.append(f"   └─ 👤 **{u_name}**: -{take} {item_name} *(Còn {remains})*")
                            
                            if u_inv[item_name] == 0:
                                del u_inv[item_name]
                            if needed_to_deduct <= 0:
                                break

                    unit_p = prices.get(item_name, 0)
                    earned = unit_p * qty
                    total_earned += earned
                    
                    price_note = f" *(Thu: {earned:,}đ)*" if unit_p > 0 else ""
                    item_detail = f"🔴 **-{qty}** {item_name}{price_note} | Tồn kho mới: `{inventory[item_name]}`"
                    if deduct_logs:
                        item_detail += "\n" + "\n".join(deduct_logs)
                    
                    details.append(item_detail)

            if details:
                save_data(data)
                await message.add_reaction("💸")
                embed = discord.Embed(
                    title="📤 XÁC NHẬN PHIẾU XUẤT BÁN KHO",
                    color=discord.Color.orange()
                )
                embed.add_field(name="👤 Người thực hiện", value=message.author.mention, inline=True)
                embed.add_field(name="🕒 Thời gian", value=f"`{now_str}`", inline=True)
                embed.add_field(name="📦 Chi tiết xuất kho", value="\n\n".join(details), inline=False)
                
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
# 7. KHỞI CHẠY ĐỒNG THỜI BOT & WEB SERVER DÀNH CHO RENDER
# =========================================================
async def main():
    print("🚀 Đang khởi động tiến trình ứng dụng...")
    
    if not TOKEN:
        print("❌ LỖI NGHIÊM TRỌNG: Chưa cấu hình DISCORD_TOKEN trong Environment!")
        return

    try:
        await start_web_server()
    except Exception as e:
        print(f"❌ Lỗi khởi tạo Web Server Port: {e}")

    try:
        print("🔑 Đang kết nối đến Discord Gateway...")
        async with bot:
            await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ Lỗi đăng nhập Discord Bot: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Tiến trình đã ngắt thủ công.")
    except Exception as e:
        print(f"💥 Lỗi dừng chương trình: {e}")