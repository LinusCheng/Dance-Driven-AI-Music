#include <magentart/realtime_runner.h>

#import <AVFoundation/AVFoundation.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <optional>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace {

using magentart::core::RealtimeRunner;

constexpr std::array<const char*, 6> kPromptNodes = {
    "node_1",
    "node_2",
    "node_3",
    "node_4",
    "node_5",
    "node_6",
};

constexpr std::array<const char*, 6> kDefaultPromptTexts = {
    "dynamic music control",
    "bright disco house groove",
    "minimal ambient texture",
    "driving techno industrial pulse",
    "cinematic experimental motion",
    "funky syncopated bass and drums",
};

double clamp(double value, double min_value, double max_value) {
    return std::max(min_value, std::min(max_value, value));
}

std::string escape_json(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch; break;
        }
    }
    return out.str();
}

std::optional<std::string> extract_string(const std::string& json, const std::string& key) {
    const std::regex pattern("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (std::regex_search(json, match, pattern)) {
        return match[1].str();
    }
    return std::nullopt;
}

std::optional<double> extract_number(const std::string& json, const std::string& key) {
    const std::regex pattern("\"" + key + "\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?)");
    std::smatch match;
    if (std::regex_search(json, match, pattern)) {
        return std::stod(match[1].str());
    }
    return std::nullopt;
}

std::string home_dir() {
    const char* home = std::getenv("HOME");
    return home == nullptr ? std::string() : std::string(home);
}

std::filesystem::path default_magenta_dir() {
    const char* override_path = std::getenv("MAGENTA_RT_DIR");
    if (override_path != nullptr && std::string(override_path).size() > 0) {
        return override_path;
    }
    return std::filesystem::path(home_dir()) / "Documents" / "Magenta" / "magenta-rt-v2";
}

std::string normalize_model_name(const std::string& raw) {
    std::string value = raw;
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    if (value == "small" || value == "mrt2_small") {
        return "mrt2_small";
    }
    if (value == "base" || value == "mrt2_base") {
        return "mrt2_base";
    }
    return "mrt2_small";
}

std::filesystem::path model_path_for_name(const std::string& model_name) {
    const std::filesystem::path root = default_magenta_dir();
    return root / "models" / model_name / (model_name + ".mlxfn");
}

std::filesystem::path resources_path() {
    return default_magenta_dir() / "resources";
}

struct EngineState {
    std::string model_name = "mrt2_small";
    std::string prompt = "";
    std::unordered_map<std::string, std::string> prompt_texts;
    std::unordered_map<std::string, double> controls;
    std::unordered_map<std::string, double> weights;
    bool assets_ready = false;
    bool model_ready = false;
    bool audio_ready = false;
    double stream_sample_rate = 48000.0;
    double device_sample_rate = 0.0;
    int output_channels = 2;
    std::string last_error;
};

double weight_value(const EngineState& state, const std::string& key, double fallback);

void initialize_state(EngineState& state) {
    for (std::size_t i = 0; i < kPromptNodes.size(); ++i) {
        state.prompt_texts[kPromptNodes[i]] = kDefaultPromptTexts[i];
        state.weights[kPromptNodes[i]] = i == 0 ? 1.0 : 0.0;
    }
    state.controls["temperature"] = 1.0;
    state.controls["top_k"] = 100.0;
    state.controls["cfg_musiccoca"] = 3.0;
    state.controls["cfg_notes"] = 5.0;
    state.controls["cfg_drums"] = 1.0;
}

void update_prompt_texts_from_json(EngineState& state, const std::string& json) {
    for (const char* node : kPromptNodes) {
        if (auto value = extract_string(json, node)) {
            state.prompt_texts[node] = *value;
        } else if (auto value = extract_string(json, node + std::string("_text"))) {
            state.prompt_texts[node] = *value;
        }
    }
}

void update_weights_from_json(EngineState& state, const std::string& json) {
    for (const char* node : kPromptNodes) {
        if (auto value = extract_number(json, node)) {
            state.weights[node] = clamp(*value, 0.0, 1.0);
        }
    }
}

std::vector<float> normalized_prompt_weights(const EngineState& state) {
    std::vector<float> weights;
    weights.reserve(kPromptNodes.size());

    double total = 0.0;
    for (const char* node : kPromptNodes) {
        total += std::max(0.0, weight_value(state, node, 0.0));
    }

    if (total <= 0.0001) {
        weights.push_back(1.0f);
        for (std::size_t i = 1; i < kPromptNodes.size(); ++i) {
            weights.push_back(0.0f);
        }
        return weights;
    }

    for (const char* node : kPromptNodes) {
        weights.push_back(static_cast<float>(std::max(0.0, weight_value(state, node, 0.0)) / total));
    }
    return weights;
}

void update_controls_from_json(EngineState& state, const std::string& json) {
    for (const std::string key : {
        "density",
        "brightness",
        "tension",
        "rhythmicActivity",
        "harmonyWidth",
        "temperature",
        "top_k",
        "cfg_musiccoca",
        "cfg_notes",
        "cfg_drums",
    }) {
        if (auto value = extract_number(json, key)) {
            state.controls[key] = *value;
        }
    }
}

double control_value(const EngineState& state, const std::string& key, double fallback) {
    auto found = state.controls.find(key);
    return found == state.controls.end() ? fallback : found->second;
}

double weight_value(const EngineState& state, const std::string& key, double fallback) {
    auto found = state.weights.find(key);
    return found == state.weights.end() ? fallback : found->second;
}

double arm_height_to_unit(const std::string& value) {
    std::string text = value;
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char ch) {
        return static_cast<char>(std::toupper(ch));
    });
    if (text == "HIGH") {
        return 1.0;
    }
    if (text == "MID") {
        return 0.5;
    }
    if (auto number = extract_number("{\"value\":" + value + "}", "value")) {
        return clamp(*number, 0.0, 1.0);
    }
    return 0.0;
}

double scale(double value, double target_min, double target_max) {
    return target_min + clamp(value, 0.0, 1.0) * (target_max - target_min);
}

std::string object_json(const std::unordered_map<std::string, double>& values,
                        const std::vector<std::string>& keys) {
    std::ostringstream out;
    out << "{";
    bool first = true;
    for (const auto& key : keys) {
        auto found = values.find(key);
        if (found == values.end()) {
            continue;
        }
        if (!first) {
            out << ",";
        }
        first = false;
        out << "\"" << key << "\":" << found->second;
    }
    out << "}";
    return out.str();
}

void emit_status(const EngineState& state, const std::string& message, bool ok = true) {
    std::cout
        << "{\"type\":\"engineStatus\","
        << "\"ok\":" << (ok ? "true" : "false") << ","
        << "\"engine\":\"GenMusicEngine\","
        << "\"message\":\"" << escape_json(message) << "\","
        << "\"modelName\":\"" << escape_json(state.model_name) << "\","
        << "\"prompt\":\"" << escape_json(state.prompt) << "\","
        << "\"assetsReady\":" << (state.assets_ready ? "true" : "false") << ","
        << "\"modelReady\":" << (state.model_ready ? "true" : "false") << ","
        << "\"audioReady\":" << (state.audio_ready ? "true" : "false") << ","
        << "\"streamSampleRate\":" << state.stream_sample_rate << ","
        << "\"deviceSampleRate\":" << state.device_sample_rate << ","
        << "\"outputChannels\":" << state.output_channels << ","
        << "\"controls\":" << object_json(state.controls, {
            "temperature", "top_k", "cfg_musiccoca", "cfg_notes", "cfg_drums",
            "density", "brightness", "tension", "rhythmicActivity", "harmonyWidth",
        }) << ","
        << "\"weights\":" << object_json(state.weights, {
            "node_1", "node_2", "node_3", "node_4", "node_5", "node_6",
        });
    if (!state.last_error.empty()) {
        std::cout << ",\"error\":\"" << escape_json(state.last_error) << "\"";
    }
    std::cout << "}" << std::endl;
}

}  // namespace

@interface AudioHost : NSObject
- (instancetype)initWithRunner:(RealtimeRunner*)runner;
- (BOOL)startWithError:(NSError**)error;
- (double)streamSampleRate;
- (double)deviceSampleRate;
- (int)outputChannels;
- (void)stop;
@end

@implementation AudioHost {
    RealtimeRunner* _runner;
    AVAudioEngine* _audioEngine;
    AVAudioSourceNode* _sourceNode;
}

- (instancetype)initWithRunner:(RealtimeRunner*)runner {
    self = [super init];
    if (self) {
        _runner = runner;
    }
    return self;
}

- (BOOL)startWithError:(NSError**)error {
    _audioEngine = [[AVAudioEngine alloc] init];
    AVAudioFormat* format = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:48000.0 channels:2];
    RealtimeRunner* runner = _runner;

    _sourceNode = [[AVAudioSourceNode alloc]
        initWithFormat:format
        renderBlock:^OSStatus(BOOL* isSilence,
                              const AudioTimeStamp* timestamp,
                              AVAudioFrameCount frameCount,
                              AudioBufferList* outputData) {
            (void)timestamp;
            float* outL = static_cast<float*>(outputData->mBuffers[0].mData);
            float* outR = outputData->mNumberBuffers > 1
                ? static_cast<float*>(outputData->mBuffers[1].mData)
                : outL;

            if (!runner->is_loaded()) {
                std::memset(outL, 0, frameCount * sizeof(float));
                if (outputData->mNumberBuffers > 1) {
                    std::memset(outR, 0, frameCount * sizeof(float));
                }
                *isSilence = YES;
                return noErr;
            }

            runner->read_audio_stereo(outL, outR, frameCount, false);
            *isSilence = NO;
            return noErr;
        }];

    [_audioEngine attachNode:_sourceNode];
    [_audioEngine connect:_sourceNode to:_audioEngine.mainMixerNode format:format];
    return [_audioEngine startAndReturnError:error];
}

- (double)streamSampleRate {
    AVAudioFormat* format = [_sourceNode outputFormatForBus:0];
    return format ? format.sampleRate : 0.0;
}

- (double)deviceSampleRate {
    AVAudioFormat* format = [_audioEngine.outputNode outputFormatForBus:0];
    return format ? format.sampleRate : 0.0;
}

- (int)outputChannels {
    AVAudioFormat* format = [_sourceNode outputFormatForBus:0];
    return format ? (int)format.channelCount : 0;
}

- (void)stop {
    [_audioEngine stop];
    _sourceNode = nil;
    _audioEngine = nil;
}

@end

namespace {

class NativeMagentaEngine {
public:
    explicit NativeMagentaEngine(EngineState& state)
        : state_(state), audio_host_([[AudioHost alloc] initWithRunner:&runner_]) {}

    bool start_audio() {
        NSError* error = nil;
        if (![audio_host_ startWithError:&error]) {
            state_.last_error = error ? error.localizedDescription.UTF8String : "AVAudioEngine failed to start";
            state_.audio_ready = false;
            return false;
        }
        state_.audio_ready = true;
        state_.stream_sample_rate = [audio_host_ streamSampleRate];
        state_.device_sample_rate = [audio_host_ deviceSampleRate];
        state_.output_channels = [audio_host_ outputChannels];
        return true;
    }

    void stop() {
        [audio_host_ stop];
        runner_.stop();
    }

    bool init_assets() {
        const std::filesystem::path resources = resources_path();
        state_.assets_ready = runner_.init_assets(resources.string().c_str());
        if (!state_.assets_ready) {
            state_.last_error = "failed to init assets from " + resources.string();
        }
        return state_.assets_ready;
    }

    bool load_model(const std::string& model_name) {
        state_.model_name = normalize_model_name(model_name);
        const std::filesystem::path path = model_path_for_name(state_.model_name);
        if (!std::filesystem::exists(path)) {
            state_.model_ready = false;
            state_.last_error = "model file missing: " + path.string();
            return false;
        }

        apply_controls();
        state_.model_ready = runner_.load_model(path.string().c_str());
        if (!state_.model_ready) {
            state_.last_error = "failed to load model: " + path.string();
            return false;
        }

        apply_prompt();
        state_.last_error.clear();
        return true;
    }

    void apply_controls() {
        runner_.set_temperature(static_cast<float>(clamp(control_value(state_, "temperature", 1.0), 0.0, 3.0)));
        runner_.set_top_k(static_cast<int>(std::round(clamp(control_value(state_, "top_k", 100.0), 1.0, 1024.0))));
        runner_.set_cfg_musiccoca(static_cast<float>(clamp(control_value(state_, "cfg_musiccoca", 3.0), 0.0, 5.0)));
        runner_.set_cfg_notes(static_cast<float>(clamp(control_value(state_, "cfg_notes", 5.0), 0.0, 5.0)));
        runner_.set_cfg_drums(static_cast<float>(clamp(control_value(state_, "cfg_drums", 1.0), 0.0, 5.0)));
    }

    void apply_prompt() {
        std::vector<std::string> texts;
        texts.reserve(kPromptNodes.size());

        for (const char* node : kPromptNodes) {
            auto found = state_.prompt_texts.find(node);
            texts.push_back(found == state_.prompt_texts.end() ? "" : found->second);
        }

        if (!state_.prompt.empty()) {
            texts[0] = state_.prompt;
        }

        std::vector<float> weights = normalized_prompt_weights(state_);
        runner_.set_text_prompts(texts, weights);
        runner_.set_blend_weights(weights.data(), static_cast<int>(weights.size()));
    }

private:
    EngineState& state_;
    RealtimeRunner runner_;
    AudioHost* audio_host_;
};

void handle_message(EngineState& state, NativeMagentaEngine& engine, const std::string& line) {
    const std::string type = extract_string(line, "type").value_or("unknown");

    if (type == "shutdown") {
        emit_status(state, "shutdown requested");
        engine.stop();
        std::exit(0);
    }

    if (type == "setModelSize") {
        const std::string model_name = normalize_model_name(extract_string(line, "modelName").value_or(state.model_name));
        const bool ok = engine.load_model(model_name);
        emit_status(state, ok ? "model loaded" : "model load failed", ok);
        return;
    }

    if (type == "updateMusicState") {
        state.prompt = extract_string(line, "prompt").value_or(state.prompt);
        update_prompt_texts_from_json(state, line);
        update_controls_from_json(state, line);
        update_weights_from_json(state, line);
        engine.apply_controls();
        engine.apply_prompt();
        emit_status(state, "music state applied");
        return;
    }

    if (type == "updateMotionControls") {
        const double left = arm_height_to_unit(extract_string(line, "leftArmHeight").value_or("LOW"));
        const double right = arm_height_to_unit(extract_string(line, "rightArmHeight").value_or("LOW"));
        state.controls["cfg_musiccoca"] = scale(left, 0.5, 5.0);
        state.controls["top_k"] = std::round(scale(right, 10.0, 500.0));
        update_prompt_texts_from_json(state, line);
        update_weights_from_json(state, line);
        engine.apply_controls();
        engine.apply_prompt();
        emit_status(state, "motion controls applied");
        return;
    }

    if (type == "updateLiveControls") {
        update_controls_from_json(state, line);
        engine.apply_controls();
        emit_status(state, "live controls applied");
        return;
    }

    emit_status(state, "unknown message ignored");
}

}  // namespace

int main() {
    @autoreleasepool {
        EngineState state;
        initialize_state(state);
        NativeMagentaEngine engine(state);

        const bool audio_ok = engine.start_audio();
        const bool assets_ok = engine.init_assets();
        const bool model_ok = assets_ok && engine.load_model(state.model_name);
        emit_status(
            state,
            audio_ok && model_ok ? "ready - native magentart::core streaming" : "startup incomplete",
            audio_ok && model_ok
        );

        std::string line;
        while (std::getline(std::cin, line)) {
            if (line.empty()) {
                continue;
            }
            handle_message(state, engine, line);
        }

        engine.stop();
    }
    return 0;
}
