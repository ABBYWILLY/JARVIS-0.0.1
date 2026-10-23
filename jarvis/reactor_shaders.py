"""Original, asset-free GLSL sources for the optional GPU reactor prototype."""

FULLSCREEN_VERTEX = """#version 330
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

REACTOR_FRAGMENT = """#version 330
in vec2 uv;
out vec4 frag;
uniform vec2 u_size;
uniform vec3 u_color;
uniform float u_time, u_reactor, u_rms;
const float TAU = 6.28318530718;
mat2 turn(float a) { return mat2(cos(a), -sin(a), sin(a), cos(a)); }
float lineGlow(float d, float width) {
    return exp(-d*d/(width*width));
}
void main() {
    vec3 light = vec3(0.0013, 0.0024, 0.0042);
    if (u_reactor <= 0.0) { frag = vec4(light, 1.0); return; }
    float aspect = u_size.x / u_size.y;
    float fit = min(1.0, aspect);
    vec2 p = (uv * 2.0 - 1.0) * vec2(aspect, 1.0) / fit;
    float r = length(p), t = u_time;
    float activation = smoothstep(0.0, 0.85, u_reactor);
    float px = 2.0 / (min(u_size.x, u_size.y));
    vec3 cold = mix(u_color, vec3(0.53, 0.83, 1.0), 0.12);
    vec3 warm = mix(u_color, vec3(1.0, 0.49, 0.20), 0.86);
    // A quiet transparent volume surrounds a compact, readable energy core.
    float breath = 1.0 + 0.055*sin(t*1.7) + 0.12*u_rms;
    light += cold * (0.026*exp(-r*r/0.31) +
              0.16*exp(-r*r/0.028) + 0.36*exp(-r*r/0.0028)) * breath * activation;
    float aperture = lineGlow(r - 0.105 - 0.006*sin(t*1.1), 0.006 + px);
    float angle = atan(p.y, p.x);
    float crown = lineGlow(r - (0.168 + 0.006*sin(angle*12.0-t*1.9)), 0.0017+px*.6);
    float petals = pow(max(0.0, cos(angle*9.0+t*.4)), 15.0);
    light += cold * activation * (aperture*1.2 + crown*(0.25+petals*0.9));
    // Five different projected orbital planes. Depth changes both width and
    // intensity; broken conductive strips keep dark windows through the volume.
    for (int i = 0; i < 5; ++i) {
        float fi = float(i);
        float rot = fi*1.117 + 0.12*sin(t*.19+fi);
        float tilt = 0.30 + 0.115*fi + .045*sin(t*.27+fi*2.0);
        vec2 q = turn(rot)*p;
        q.y /= tilt;
        float a = atan(q.y, q.x);
        float radius = .34 + fi*.105;
        float wave = .0025*sin(a*13.0+t*.7+fi);
        float d = (length(q)-radius-wave)*tilt;
        float depth = .52 + .48*sin(a);
        float phase = a + t*(.12+fi*.035)*(mod(fi,2.0)*2.0-1.0) + fi;
        float sectors = .5+.5*sin(phase*(9.0+fi*2.0));
        float segment = smoothstep(.20,.31,sectors);
        float highlight = pow(max(0.0, cos(phase*2.0+fi)),18.0);
        float width = (0.0015 + px*.58)*(0.75+depth*.55);
        float rail = lineGlow(d,width) * segment;
        float outer = lineGlow(abs(d)-.008,width*.68) * smoothstep(.58,.71,sectors);
        float halo = lineGlow(d,.013) * .07 * segment;
        vec3 tint = mix(cold, warm, float(i == 3)*.68);
        light += tint * (rail*(.45+depth*1.55+highlight*1.3) + outer*.32+halo) * activation;
        // Moving charge packets are attached to the orbital plane, not the UI.
        float packet = pow(max(0.0,cos(phase*3.0+fi)),95.0);
        light += tint*lineGlow(d,.006+px)*packet*(.5+depth)*activation;
    }
    float spokes = pow(max(0.0,cos(angle*17.0 + .6*sin(angle*5.0+t*.35))),34.0);
    light += cold*spokes*exp(-pow((r-.21)/.055,2.0))*.12*activation;
    frag = vec4(light, 1.0);
}
"""

CURVE_VERTEX = """#version 330
in vec2 a_start, a_end, a_range;
in float a_main;
uniform vec2 u_size;
uniform float u_reactor, u_time, u_rms, u_detail_opacity;
out vec2 v_local;
flat out float v_length, v_strength;
vec2 position(vec2 source, float u) {
    if (a_main < .5 || u_reactor <= 0.0) return source;
    float a = u*25.13274123 - u_time*.32;
    float radius = .035 + .25*u;
    vec2 spiral = vec2(cos(a)*radius, sin(a)*radius*.72);
    float aspect = u_size.x/u_size.y;
    spiral *= min(1.0,aspect);
    spiral.x /= aspect;
    return mix(source, spiral, smoothstep(0.0,1.0,u_reactor));
}
void main() {
    vec2 start = position(a_start,a_range.x)*u_size*.5;
    vec2 end = position(a_end,a_range.y)*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = length_ > .0001 ? delta/length_ : vec2(1.0,0.0);
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1) == 0 ? -1.0 : 1.0;
    float along = gl_VertexID < 2 ? -10.0 : length_+10.0;
    vec2 pixel = start+tangent*along+normal*side*10.0;
    gl_Position = vec4(pixel*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*10.0);
    v_length = length_;
    v_strength = a_main > .5 ? 1.0 : (1.0-smoothstep(0.0,.8,u_reactor))*u_detail_opacity;
}
"""

CURVE_FRAGMENT = """#version 330
in vec2 v_local;
flat in float v_length, v_strength;
uniform vec3 u_color;
uniform float u_rms;
out vec4 frag;
void main() {
    float d = length(vec2(v_local.x-clamp(v_local.x,0.0,v_length),v_local.y));
    float core = exp(-d*d/0.62);
    float shoulder = exp(-d*d/3.2)*.26;
    float halo = exp(-d*d/24.0)*.024;
    vec3 tint = mix(u_color,vec3(1.0),.16);
    frag = vec4(tint*(core*1.45+shoulder+halo)*(1.0+.4*u_rms)*v_strength,1.0);
}
"""

FILAMENT_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor;
out vec2 v_local;
flat out float v_length, v_strength;
const int STEPS = 144;
vec2 path(float u, float strand) {
    float t = u_time;
    float theta = u*6.2831853 + strand*1.04719755;
    float a = theta*2.0 + t*(.21+strand*.018);
    float radius = .23 + .038*sin(theta*3.0+t*.43+strand);
    vec3 p = vec3(cos(a)*radius,sin(a)*radius,.16*sin(theta+strand*.7));
    float tilt = .65+strand*.29;
    p.yz = mat2(cos(tilt),-sin(tilt),sin(tilt),cos(tilt))*p.yz;
    p.xy = mat2(cos(strand*.51),-sin(strand*.51),sin(strand*.51),cos(strand*.51))*p.xy;
    vec2 xy = p.xy/(1.0-p.z*.45);
    float aspect = u_size.x/u_size.y;
    return xy*min(1.0,aspect)/vec2(aspect,1.0);
}
void main() {
    float strand = float(gl_InstanceID/STEPS);
    float u = float(gl_InstanceID%STEPS)/float(STEPS);
    vec2 start = path(u,strand)*u_size*.5;
    vec2 end = path(u+1.0/float(STEPS),strand)*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = normalize(delta+vec2(.00001,0.0));
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1) == 0 ? -1.0 : 1.0;
    float along = gl_VertexID < 2 ? -5.0 : length_+5.0;
    gl_Position = vec4((start+tangent*along+normal*side*5.0)*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*5.0);
    v_length = length_;
    v_strength = u_reactor*.29*(.4+.6*pow(.5+.5*sin(u*31.4159-u_time*.7+strand),2.0));
}
"""

PARTICLE_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor, u_rms;
out float v_power, v_warm;
float hash(float n) { return fract(sin(n*127.1+311.7)*43758.5453); }
void main() {
    float id = float(gl_VertexID);
    float seed = hash(id+1.0);
    float radius = .17 + pow(hash(id+11.0),.7)*.63;
    float a = seed*6.2831853 + u_time*(.035+hash(id+3.0)*.12)*(mod(id,2.0)*2.0-1.0);
    float latitude = (hash(id+91.0)-.5)*1.8;
    vec3 p = vec3(cos(a)*radius, sin(a)*radius*.67, sin(a+latitude)*radius*.43);
    p.xy += vec2(sin(a*3.0+latitude),cos(a*2.0+latitude))*.012;
    float aspect = u_size.x/u_size.y;
    vec2 projected = p.xy/(1.0-p.z*.35)*min(1.0,aspect)/vec2(aspect,1.0);
    gl_Position = vec4(projected,0.0,1.0);
    float twinkle = pow(.5+.5*sin(u_time*(.5+seed)+id),5.0);
    gl_PointSize = (1.8+hash(id+6.0)*3.5)*(1.0+u_rms*.3);
    v_power = (.08+.6*twinkle)*u_reactor*(.65+p.z);
    v_warm = step(.91,hash(id+17.0));
}
"""

PARTICLE_FRAGMENT = """#version 330
in float v_power, v_warm;
uniform vec3 u_color;
out vec4 frag;
void main() {
    vec2 p = gl_PointCoord*2.0-1.0;
    float r2 = dot(p,p);
    if (r2>1.0) discard;
    vec3 tint = mix(u_color,vec3(1.0,.53,.24),v_warm*.85);
    frag = vec4(tint*exp(-r2*5.5)*v_power*2.1,1.0);
}
"""

EXTRACT_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_source_size;
out vec4 frag;
void main() {
    vec3 light = vec3(0.0);
    for (int y=0;y<4;++y) for (int x=0;x<4;++x) {
        vec2 offset = (vec2(x,y)-1.5)/u_source_size;
        vec3 c = texture(u_image,uv+offset).rgb;
        float peak = max(c.r,max(c.g,c.b));
        light += c*smoothstep(.15,1.15,peak);
    }
    frag = vec4(light/16.0,1.0);
}
"""

BLUR_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_step;
out vec4 frag;
void main() {
    vec3 c = texture(u_image,uv).rgb*.227027;
    c += (texture(u_image,uv+u_step*1.384615).rgb + texture(u_image,uv-u_step*1.384615).rgb)*.316216;
    c += (texture(u_image,uv+u_step*3.230769).rgb + texture(u_image,uv-u_step*3.230769).rgb)*.070270;
    frag = vec4(c,1.0);
}
"""

RESOLVE_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image, u_bloom;
uniform float u_bloom_amount;
out vec4 frag;
void main() {
    vec3 light = texture(u_image,uv).rgb + texture(u_bloom,uv).rgb*u_bloom_amount;
    vec3 mapped = 1.0-exp(-light*.88);
    frag = vec4(pow(max(mapped,vec3(0.0)),vec3(1.0/2.2)),1.0);
}
"""

COPY_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
out vec4 frag;
void main() { frag = vec4(texture(u_image,uv).rgb,1.0); }
"""
